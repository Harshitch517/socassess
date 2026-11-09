"""SOCAssess REST API.

    python -m uvicorn socassess.api.app:app --app-dir backend --port 8000

Settings (environment variables):
  SOCASSESS_DB              path to the DuckDB store (default data/processed/socassess.duckdb)
  SOCASSESS_CORS_ORIGINS    comma-separated allowed origins (default: local Vite dev server)
  SOCASSESS_MAX_UPLOAD_MB   upload size limit (default 200)
  SOCASSESS_READ_ONLY       "1" disables upload and analysis runs (public demo)
  SOCASSESS_FRONTEND_DIR    optional folder with the built frontend, served at /
"""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import socassess
from socassess.analytics.engine import latest_run_id, persist, run_analysis
from socassess.api import reports
from socassess.api.db import Database
from socassess.config import DB_PATH
from socassess.ingestion.loaders import LoadError
from socassess.ingestion.pipeline import ingest_path
from socassess.ingestion.validate import ValidationError

UPLOAD_SUFFIXES = {".zip", ".csv", ".json", ".jsonl", ".sqlite", ".sqlite3", ".db", ".duckdb", ".parquet",
                   ".xlsx", ".xlsm"}


class Settings:
    def __init__(self) -> None:
        self.db_path = os.environ.get("SOCASSESS_DB", str(DB_PATH))
        self.cors = [o.strip() for o in os.environ.get(
            "SOCASSESS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
        self.max_upload_mb = int(os.environ.get("SOCASSESS_MAX_UPLOAD_MB", "200"))
        self.read_only = os.environ.get("SOCASSESS_READ_ONLY", "0") == "1"
        self.frontend_dir = os.environ.get("SOCASSESS_FRONTEND_DIR")


class RunRequest(BaseModel):
    params: dict = Field(default_factory=dict, description="parameter overrides (see params.py)")
    entity_ids: list[str] | None = None


def _db(request: Request) -> Database:
    return request.app.state.db


# Module-level aliases: FastAPI resolves string annotations against module globals.
DB = Annotated[Database, Depends(_db)]
RunQ = Annotated[str | None, Query(description="analysis run id (default: latest)")]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db = Database(settings.db_path)
        yield
        app.state.db.close()

    app = FastAPI(title="SOCAssess API", version=socassess.__version__, lifespan=lifespan,
                  description="Supervisory analytics for SOC assessment: findings, risk scores, evidence.")
    app.state.settings = settings
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors, allow_methods=["GET", "POST"],
                       allow_headers=["*"])

    def run_or_404(d: Database, run_id: str | None) -> str:
        with d.connection() as con:
            rid = run_id or latest_run_id(con)
        if not rid or not d.scalar("SELECT count(*) FROM analysis_runs WHERE run_id = ?", [rid]):
            raise HTTPException(404, "No analysis run found. Ingest data and run the analysis first.")
        return rid

    def writable() -> None:
        if settings.read_only:
            raise HTTPException(403, "This deployment is read-only (demo mode).")

    FINDING_COLS = ("finding_id, entity_id, type, category, severity, title, rationale, evidence_kind, "
                    "n_evidence, metric_values, detector, points")

    # ------------------------------------------------------------------ meta
    @app.get("/api/health")
    def health(d: DB):
        with d.connection() as con:
            rid = latest_run_id(con)
        return {"status": "ok", "version": socassess.__version__, "read_only": settings.read_only,
                "latest_run": rid, "entities": d.scalar("SELECT count(*) FROM entities")}

    @app.get("/api/runs")
    def runs(d: DB, limit: int = Query(50, le=500)):
        """Audit log of analysis runs: input hash, parameters hash, code version, timestamp."""
        return d.rows("SELECT * EXCLUDE (params) FROM analysis_runs ORDER BY started_at DESC LIMIT ?", [limit])

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str, d: DB):
        r = d.one("SELECT * FROM analysis_runs WHERE run_id = ?", [run_id])
        if not r:
            raise HTTPException(404, f"Unknown run {run_id}")
        return r

    @app.get("/api/ingestions")
    def ingestions(d: DB, limit: int = Query(100, le=1000)):
        return d.rows("SELECT * FROM ingest_runs ORDER BY started_at DESC LIMIT ?", [limit])

    # ------------------------------------------------------------------ write
    @app.post("/api/ingest", dependencies=[Depends(writable)])
    def ingest(d: DB, files: Annotated[list[UploadFile], File(description="export files or a .zip")],
               analyse: bool = True,
               entity_name: Annotated[str | None, Query(max_length=80, description=(
                   "organisation name for data without an organisation column"))] = None):
        """Upload data: a schema export (.zip, database file, table files) or any alert export (CSV/JSON),
        which is mapped automatically; the assumptions come back in `warnings` ('auto-mapping: ...')."""
        limit = settings.max_upload_mb * 1024 * 1024
        tmp = Path(tempfile.mkdtemp(prefix="socassess_upload_"))
        try:
            total = 0
            for f in files:
                name = Path(f.filename or "upload").name
                if Path(name).suffix.lower() not in UPLOAD_SUFFIXES:
                    raise HTTPException(415, f"{name}: unsupported file type; use {sorted(UPLOAD_SUFFIXES)}")
                with (tmp / name).open("wb") as out:
                    while chunk := f.file.read(1 << 20):
                        total += len(chunk)
                        if total > limit:
                            raise HTTPException(413, f"Upload exceeds {settings.max_upload_mb} MB")
                        out.write(chunk)
            names = [Path(f.filename or "upload").name for f in files]
            # loaders read table and database files from a folder; only a lone .zip is passed directly
            target = tmp / names[0] if len(names) == 1 and names[0].lower().endswith(".zip") else tmp
            try:
                with d.connection() as con:
                    res = ingest_path(con, target, source="upload", entity_name=entity_name or Path(names[0]).stem,
                                      source_name=", ".join(names)[:200])
                    out = {"run_id": res.run_id, "input_sha256": res.input_sha256, "entity_ids": res.entity_ids,
                           "row_counts": res.row_counts, "warnings": res.warnings}
                    if analyse:
                        ar = run_analysis(con)
                        persist(con, ar, trigger="upload")
                        out["analysis_run_id"] = ar.run_id
            except ValidationError as e:
                raise HTTPException(422, {"message": "Validation failed", "errors": e.report.errors,
                                          "warnings": e.report.warnings}) from e
            except LoadError as e:
                raise HTTPException(422, {"message": str(e), "errors": [str(e)]}) from e
            return out
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @app.post("/api/analysis/run", dependencies=[Depends(writable)])
    def analysis_run(d: DB, body: RunRequest | None = None):
        body = body or RunRequest()
        with d.connection() as con:
            res = run_analysis(con, body.params, body.entity_ids)
            persist(con, res, trigger="api", entity_ids=body.entity_ids)
        return {"run_id": res.run_id, "duration_s": res.duration_s, "input_hash": res.input_hash,
                "code_version": res.code_version, "n_findings": len(res.findings),
                "detector_errors": res.detector_errors}

    @app.get("/api/params/default")
    def default_params():
        from socassess.analytics.params import DEFAULT_PARAMS
        return DEFAULT_PARAMS

    # ------------------------------------------------------------------ entities
    @app.get("/api/entities")
    def entities(d: DB, run_id: RunQ = None, source: str | None = None):
        rid = run_or_404(d, run_id)
        sql = "SELECT * EXCLUDE (run_id) FROM entity_scores WHERE run_id = ?"
        params: list = [rid]
        if source:
            sql += " AND source = ?"
            params.append(source)
        return {"run_id": rid, "entities": d.rows(sql + " ORDER BY rank", params)}

    @app.get("/api/entities/{entity_id}")
    def entity_detail(entity_id: str, d: DB, run_id: RunQ = None):
        rid = run_or_404(d, run_id)
        ent = d.one("SELECT * FROM entities WHERE entity_id = ?", [entity_id])
        if not ent:
            raise HTTPException(404, f"Unknown entity {entity_id}")
        score = d.one("SELECT * EXCLUDE (run_id) FROM entity_scores WHERE run_id = ? AND entity_id = ?",
                      [rid, entity_id])
        counts = d.one("""SELECT (SELECT count(*) FROM alerts WHERE entity_id = $1) AS alerts,
                                 (SELECT count(*) FROM cases WHERE entity_id = $1) AS cases,
                                 (SELECT count(*) FROM escalations WHERE entity_id = $1) AS escalations,
                                 (SELECT count(*) FROM assets WHERE entity_id = $1) AS assets,
                                 (SELECT count(*) FROM assets WHERE entity_id = $1 AND criticality = 'critical')
                                    AS critical_assets,
                                 (SELECT min(ts) FROM alerts WHERE entity_id = $1) AS first_alert,
                                 (SELECT max(ts) FROM alerts WHERE entity_id = $1) AS last_alert""", [entity_id])
        return {"run_id": rid, "entity": ent, "score": score, "counts": counts,
                "findings": d.rows(f"SELECT {FINDING_COLS} FROM findings WHERE run_id = ? AND entity_id = ? "
                                   "ORDER BY points DESC", [rid, entity_id]),
                "benchmarks": d.rows("SELECT * EXCLUDE (run_id) FROM entity_benchmarks WHERE run_id = ? AND "
                                     "entity_id = ? ORDER BY metric", [rid, entity_id]),
                "peer_values": {r["metric"]: r["values"] for r in d.rows(
                    """SELECT b.metric, list(b.value ORDER BY b.entity_id) AS values
                       FROM entity_benchmarks b JOIN entities e USING (entity_id)
                       WHERE b.run_id = ? AND b.entity_id <> ?
                         AND e.source = (SELECT source FROM entities WHERE entity_id = ?)
                       GROUP BY 1""", [rid, entity_id, entity_id])},
                "categories": d.rows("SELECT category, count(*) AS alerts FROM alerts WHERE entity_id = ? "
                                     "GROUP BY 1 ORDER BY 2 DESC", [entity_id])}

    # ------------------------------------------------------------------ findings
    @app.get("/api/findings")
    def findings(d: DB, run_id: RunQ = None, entity_id: str | None = None, type: str | None = None,
                 severity: str | None = None, category: str | None = None,
                 limit: int = Query(200, le=1000), offset: int = Query(0, ge=0)):
        rid = run_or_404(d, run_id)
        where, params = ["run_id = ?"], [rid]
        for col, val in (("entity_id", entity_id), ("type", type), ("severity", severity),
                         ("category", category)):
            if val:
                vals = val.split(",")
                where.append(f"{col} IN ({', '.join('?' * len(vals))})")
                params += vals
        w = " AND ".join(where)
        total = d.scalar(f"SELECT count(*) FROM findings WHERE {w}", params)
        rows = d.rows(f"SELECT {FINDING_COLS} FROM findings WHERE {w} ORDER BY points DESC, entity_id "
                      f"LIMIT ? OFFSET ?", params + [limit, offset])
        return {"run_id": rid, "total": total, "findings": rows}

    @app.get("/api/findings/{finding_id}")
    def finding_detail(finding_id: str, d: DB, run_id: RunQ = None,
                       limit: int = Query(50, le=500), offset: int = Query(0, ge=0)):
        rid = run_or_404(d, run_id)
        f = d.one(f"SELECT {FINDING_COLS} FROM findings WHERE run_id = ? AND finding_id = ?", [rid, finding_id])
        if not f:
            raise HTTPException(404, f"Unknown finding {finding_id} in run {rid}")
        return {"run_id": rid, "finding": f, "evidence": evidence(d, rid, finding_id, limit, offset)}

    def evidence(d: Database, rid: str, finding_id: str, limit: int, offset: int) -> dict:
        ids = d.df("SELECT unnest(evidence_ids) AS id FROM findings WHERE run_id = ? AND finding_id = ?",
                   [rid, finding_id])
        total = len(ids)
        page = ids.id.iloc[offset:offset + limit].tolist()
        if not page:
            return {"total": total, "offset": offset, "records": []}
        cases = d.rows("""SELECT 'case' AS record_type, c.case_id AS record_id, c.case_id, c.alert_id,
                    a.ts AS alert_ts, a.category, a.severity, a.rule_name, a.asset_id, s.criticality,
                    c.assignee, c.opened_at, c.closed_at, c.sla_deadline,
                    round(epoch(c.closed_at - c.opened_at) / 60, 2) AS minutes_to_close, c.status,
                    c.disposition, c.escalated, (e.case_id IS NOT NULL) AS escalation_recorded, c.remediation,
                    c.notes
             FROM cases c LEFT JOIN alerts a USING (alert_id) LEFT JOIN assets s ON s.asset_id = a.asset_id
             LEFT JOIN (SELECT DISTINCT case_id FROM escalations) e ON e.case_id = c.case_id
             WHERE c.case_id IN (SELECT unnest(?))""", [page])
        found = {r["record_id"] for r in cases}
        rest = [i for i in page if i not in found]
        alerts = d.rows("""SELECT 'alert' AS record_type, a.alert_id AS record_id, a.*, s.criticality
                           FROM alerts a LEFT JOIN assets s USING (asset_id)
                           WHERE a.alert_id IN (SELECT unnest(?))""", [rest]) if rest else []
        found |= {r["record_id"] for r in alerts}
        rest = [i for i in rest if i not in found]
        assets = d.rows("""SELECT 'asset' AS record_type, s.asset_id AS record_id, s.*,
                    (SELECT count(*) FROM alerts a WHERE a.asset_id = s.asset_id) AS alerts,
                    (SELECT count(*) FROM telemetry t WHERE t.asset_id = s.asset_id) AS telemetry_days,
                    (SELECT avg(CASE WHEN event_count = 0 THEN 1 ELSE 0 END) FROM telemetry t
                       WHERE t.asset_id = s.asset_id) AS zero_day_share,
                    (SELECT median(event_count) FROM telemetry t WHERE t.asset_id = s.asset_id) AS median_events
             FROM assets s WHERE s.asset_id IN (SELECT unnest(?))""", [rest]) if rest else []
        order = {i: n for n, i in enumerate(page)}
        records = sorted(cases + alerts + assets, key=lambda r: order.get(r["record_id"], 0))
        return {"total": total, "offset": offset, "records": records}

    @app.get("/api/findings/{finding_id}/evidence")
    def finding_evidence(finding_id: str, d: DB, run_id: RunQ = None,
                         limit: int = Query(50, le=500), offset: int = Query(0, ge=0)):
        rid = run_or_404(d, run_id)
        return evidence(d, rid, finding_id, limit, offset)

    # ------------------------------------------------------------------ records
    @app.get("/api/records/{kind}/{record_id}")
    def record(kind: Literal["case", "alert", "asset"], record_id: str, d: DB):
        if kind == "case":
            c = d.one("SELECT * FROM cases WHERE case_id = ?", [record_id])
            if not c:
                raise HTTPException(404, f"Unknown case {record_id}")
            c["alert"] = d.one("SELECT * FROM alerts WHERE alert_id = ?", [c["alert_id"]])
            c["escalations"] = d.rows("SELECT * FROM escalations WHERE case_id = ?", [record_id])
            return c
        if kind == "alert":
            a = d.one("SELECT * FROM alerts WHERE alert_id = ?", [record_id])
            if not a:
                raise HTTPException(404, f"Unknown alert {record_id}")
            a["case"] = d.one("SELECT * FROM cases WHERE alert_id = ? OR case_id = ?", [record_id, a["case_id"]])
            return a
        s = d.one("SELECT * FROM assets WHERE asset_id = ?", [record_id])
        if not s:
            raise HTTPException(404, f"Unknown asset {record_id}")
        s["telemetry"] = d.rows("SELECT date, event_count FROM telemetry WHERE asset_id = ? ORDER BY date",
                                [record_id])
        s["recent_alerts"] = d.rows("SELECT * FROM alerts WHERE asset_id = ? ORDER BY ts DESC LIMIT 50", [record_id])
        return s

    # ------------------------------------------------------------------ overview
    @app.get("/api/heatmap")
    def heatmap(d: DB, run_id: RunQ = None):
        """Entity x finding-type matrix of risk points (and severity) for the overview heatmap."""
        rid = run_or_404(d, run_id)
        cells = d.rows("""SELECT entity_id, type, sum(points) AS points, count(*) AS findings
                          FROM findings WHERE run_id = ? GROUP BY 1, 2""", [rid])
        sev = d.rows("SELECT entity_id, type, severity FROM findings WHERE run_id = ?", [rid])
        rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        worst: dict = {}
        for r in sev:
            k = (r["entity_id"], r["type"])
            worst[k] = max(worst.get(k, "low"), r["severity"], key=rank.get)
        for c in cells:
            c["severity"] = worst[(c["entity_id"], c["type"])]
        ents = d.rows("SELECT entity_id, name, risk_score, rank FROM entity_scores WHERE run_id = ? ORDER BY rank",
                      [rid])
        from socassess.analytics.params import DEFAULT_PARAMS
        return {"run_id": rid, "entities": ents, "types": list(DEFAULT_PARAMS["risk_weights"]), "cells": cells}

    @app.get("/api/summary")
    def summary(d: DB, run_id: RunQ = None,
                entity_id: Annotated[str | None, Query(description="comma-separated entity ids")] = None):
        """Totals and part-to-whole breakdowns (for the pie charts), optionally for some entities only."""
        rid = run_or_404(d, run_id)
        ids = [e for e in (entity_id or "").split(",") if e]
        f = " AND entity_id IN (SELECT unnest($ids))" if ids else ""
        p = {"rid": rid, "ids": ids} if ids else {"rid": rid}
        cats = d.rows(f"SELECT category, count(*) AS n FROM alerts WHERE true {f} GROUP BY 1 ORDER BY 2 DESC",
                      {"ids": ids} if ids else None)
        top, rest = cats[:6], sum(c["n"] for c in cats[6:])
        if rest:
            top.append({"category": "other", "n": rest})
        return {"run": d.one("SELECT * EXCLUDE (params) FROM analysis_runs WHERE run_id = ?", [rid]),
                "entity_ids": ids,
                "bands": d.rows(f"SELECT band, count(*) AS n FROM entity_scores WHERE run_id = $rid {f} GROUP BY 1", p),
                "by_type": d.rows(f"SELECT type, category, count(*) AS n, sum(points) AS points FROM findings "
                                  f"WHERE run_id = $rid {f} GROUP BY 1, 2 ORDER BY points DESC", p),
                "by_severity": d.rows(f"SELECT severity, count(*) AS n FROM findings WHERE run_id = $rid {f} "
                                      "GROUP BY 1", p),
                "by_category": d.rows(f"SELECT category, count(*) AS n, sum(points) AS points FROM findings "
                                      f"WHERE run_id = $rid {f} GROUP BY 1", p),
                "alert_severity": d.rows(f"SELECT severity, count(*) AS n FROM alerts WHERE true {f} GROUP BY 1",
                                         {"ids": ids} if ids else None),
                "alert_category": top,
                "totals": d.one(f"""SELECT (SELECT count(*) FROM entities WHERE true {f}) AS entities,
                                          (SELECT count(*) FROM alerts WHERE true {f}) AS alerts,
                                          (SELECT count(*) FROM cases WHERE true {f}) AS cases,
                                          (SELECT count(*) FROM findings WHERE run_id = $rid {f}) AS findings,
                                   (SELECT count(*) FROM review_queue WHERE run_id = $rid {f}) AS review_items""",
                                p)}

    # ------------------------------------------------------------------ clusters / trends / queue
    @app.get("/api/clusters")
    def clusters(d: DB, run_id: RunQ = None, entity_id: str | None = None):
        rid = run_or_404(d, run_id)
        rows = d.rows("SELECT * EXCLUDE (run_id) FROM pattern_clusters WHERE run_id = ? ORDER BY alerts DESC", [rid])
        if entity_id:
            rows = [r for r in rows if entity_id in r["entities"]]
        noise = d.one("SELECT count(*) AS patterns, coalesce(sum(alerts), 0) AS alerts FROM alert_patterns "
                      "WHERE run_id = ? AND cluster_id = -1", [rid])
        return {"run_id": rid, "clusters": rows, "unclustered": noise}

    @app.get("/api/clusters/{cluster_id}")
    def cluster_detail(cluster_id: int, d: DB, run_id: RunQ = None):
        rid = run_or_404(d, run_id)
        c = d.one("SELECT * EXCLUDE (run_id) FROM pattern_clusters WHERE run_id = ? AND cluster_id = ?",
                  [rid, cluster_id])
        if not c and cluster_id != -1:
            raise HTTPException(404, f"Unknown cluster {cluster_id}")
        c = c or {"cluster_id": -1, "label": "Unclustered (one-off patterns)"}
        c["patterns"] = d.rows("SELECT * EXCLUDE (run_id) FROM alert_patterns WHERE run_id = ? AND cluster_id = ? "
                               "ORDER BY alerts DESC LIMIT 500", [rid, cluster_id])
        return c

    @app.get("/api/trends")
    def trends(d: DB, run_id: RunQ = None, entity_id: str | None = None):
        rid = run_or_404(d, run_id)
        sql, params = "SELECT * EXCLUDE (run_id) FROM weekly_trends WHERE run_id = ?", [rid]
        if entity_id:
            ids = entity_id.split(",")
            sql += f" AND entity_id IN ({', '.join('?' * len(ids))})"
            params += ids
        return {"run_id": rid, "weeks": d.rows(sql + " ORDER BY entity_id, week", params)}

    @app.get("/api/review-queue")
    def review_queue(d: DB, run_id: RunQ = None, entity_id: str | None = None,
                     include_spot_checks: bool = True, limit: int = Query(200, le=2000),
                     offset: int = Query(0, ge=0)):
        rid = run_or_404(d, run_id)
        where, params = ["q.run_id = ?"], [rid]
        if entity_id:
            where.append("q.entity_id = ?")
            params.append(entity_id)
        if not include_spot_checks:
            where.append("q.finding_type <> 'spot_check'")
        w = " AND ".join(where)
        total = d.scalar(f"SELECT count(*) FROM review_queue q WHERE {w}", params)
        rows = d.rows(f"""SELECT q.* EXCLUDE (run_id), f.title AS finding_title, s.name AS entity_name
                          FROM review_queue q
                          LEFT JOIN findings f ON f.run_id = q.run_id AND f.finding_id = q.finding_id
                          LEFT JOIN entity_scores s ON s.run_id = q.run_id AND s.entity_id = q.entity_id
                          WHERE {w} ORDER BY q.rank LIMIT ? OFFSET ?""", params + [limit, offset])
        return {"run_id": rid, "total": total, "items": rows}

    # ------------------------------------------------------------------ reports
    @app.get("/api/reports/{name}.csv")
    def report_csv(name: Literal["entities", "findings", "review_queue", "benchmarks"], d: DB, run_id: RunQ = None):
        rid = run_or_404(d, run_id)
        table = {"entities": "entity_scores", "findings": "findings", "review_queue": "review_queue",
                 "benchmarks": "entity_benchmarks"}[name]
        rows = d.rows(f"SELECT * FROM {table} WHERE run_id = ?", [rid])
        return Response(reports.to_csv(rows), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="socassess_{name}_{rid}.csv"'})

    @app.get("/api/reports/summary.pdf")
    def report_summary_pdf(d: DB, run_id: RunQ = None):
        rid = run_or_404(d, run_id)
        run = d.one("SELECT * FROM analysis_runs WHERE run_id = ?", [rid])
        scores = d.rows("SELECT * FROM entity_scores WHERE run_id = ? ORDER BY rank", [rid])
        fs = d.rows("SELECT * EXCLUDE (evidence_ids) FROM findings WHERE run_id = ?", [rid])
        return Response(reports.summary_pdf(run, scores, fs), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="socassess_summary_{rid}.pdf"'})

    @app.get("/api/reports/entity/{entity_id}.pdf")
    def report_entity_pdf(entity_id: str, d: DB, run_id: RunQ = None):
        rid = run_or_404(d, run_id)
        ent = d.one("SELECT * FROM entities WHERE entity_id = ?", [entity_id])
        score = d.one("SELECT * FROM entity_scores WHERE run_id = ? AND entity_id = ?", [rid, entity_id])
        if not ent or not score:
            raise HTTPException(404, f"Unknown entity {entity_id}")
        run = d.one("SELECT * FROM analysis_runs WHERE run_id = ?", [rid])
        fs = d.rows("SELECT * EXCLUDE (evidence_ids) FROM findings WHERE run_id = ? AND entity_id = ?",
                    [rid, entity_id])
        bench = d.rows("SELECT * FROM entity_benchmarks WHERE run_id = ? AND entity_id = ? ORDER BY metric",
                       [rid, entity_id])
        q = d.rows("SELECT * FROM review_queue WHERE run_id = ? AND entity_id = ? ORDER BY rank", [rid, entity_id])
        pdf = reports.entity_pdf(run, ent, score, fs, bench, q)
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="socassess_{entity_id}_{rid}.pdf"'})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": exc.detail}
        return JSONResponse(detail, status_code=exc.status_code)

    # ------------------------------------------------------------------ optional bundled frontend
    if settings.frontend_dir and Path(settings.frontend_dir, "index.html").exists():
        fdir = Path(settings.frontend_dir)
        app.mount("/assets", StaticFiles(directory=fdir / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = (fdir / path).resolve()
            if path and f.is_file() and fdir.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(fdir / "index.html")

    return app


app = create_app()
