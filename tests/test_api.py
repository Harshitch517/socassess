import io
import zipfile

import pandas as pd
import pytest
from conftest import world
from fastapi.testclient import TestClient

from socassess import store
from socassess.analytics.engine import persist, run_analysis
from socassess.api.app import Settings, create_app
from socassess.ingestion.pipeline import ingest_tables


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    t = world()
    tel = t["telemetry"]
    tel.loc[tel.asset_id.isin(["E6-A00", "E6-A01"]), "event_count"] = 0  # plant a silent-asset finding
    path = tmp_path_factory.mktemp("api") / "test.duckdb"
    con = store.connect(path)
    ingest_tables(con, t, source_name="test", input_sha256="0" * 64, source="synthetic")
    persist(con, run_analysis(con), trigger="test")
    con.close()
    return path


def client(db_path, **kw):
    s = Settings()
    s.db_path, s.read_only = str(db_path), kw.get("read_only", False)
    return TestClient(create_app(s))


@pytest.fixture(scope="module")
def api(db_path):
    with client(db_path) as c:
        yield c


def test_health_and_runs(api):
    h = api.get("/api/health").json()
    assert h["status"] == "ok" and h["entities"] == 8 and h["latest_run"]
    runs = api.get("/api/runs").json()
    assert runs[0]["run_id"] == h["latest_run"] and len(runs[0]["input_hash"]) == 64
    detail = api.get(f"/api/runs/{h['latest_run']}").json()
    assert detail["params"]["z_min"] == 3.0
    assert api.get("/api/runs/nope").status_code == 404


def test_entities_and_detail(api):
    ents = api.get("/api/entities").json()["entities"]
    assert len(ents) == 8 and ents[0]["entity_id"] == "E6" and ents[0]["risk_score"] > 0
    assert ents[0]["breakdown"][0]["type"] == "silent_critical_assets"
    d = api.get("/api/entities/E6").json()
    assert d["entity"]["name"] == "Entity 6" and d["counts"]["critical_assets"] == 3
    assert d["findings"][0]["type"] == "silent_critical_assets"
    assert {b["metric"] for b in d["benchmarks"]} >= {"fast_close_share", "escalation_rate_crit_tp"}
    assert len(d["peer_values"]["fast_close_share"]) == 7
    assert api.get("/api/entities/NOPE").status_code == 404


def test_findings_filter_and_evidence(api):
    all_f = api.get("/api/findings").json()
    assert all_f["total"] >= 1
    f = api.get("/api/findings", params={"type": "silent_critical_assets"}).json()["findings"]
    assert len(f) == 1 and f[0]["entity_id"] == "E6"
    assert api.get("/api/findings", params={"entity_id": "E0", "type": "silent_critical_assets"}).json()["total"] == 0
    det = api.get(f"/api/findings/{f[0]['finding_id']}").json()
    ev = det["evidence"]
    assert ev["total"] == 2 and {r["record_id"] for r in ev["records"]} == {"E6-A00", "E6-A01"}
    assert ev["records"][0]["record_type"] == "asset" and ev["records"][0]["zero_day_share"] == 1.0
    assert api.get("/api/findings/doesnotexist").status_code == 404


def test_records(api):
    case = api.get("/api/records/case/E1-CS00001").json()
    assert case["alert"]["alert_id"] == "E1-AL00001"
    asset = api.get("/api/records/asset/E6-A00").json()
    assert len(asset["telemetry"]) == 60
    assert api.get("/api/records/case/missing").status_code == 404
    assert api.get("/api/records/widget/x").status_code == 422


def test_overview_endpoints(api):
    hm = api.get("/api/heatmap").json()
    assert any(c["entity_id"] == "E6" and c["type"] == "silent_critical_assets" for c in hm["cells"])
    s = api.get("/api/summary").json()
    assert s["totals"]["entities"] == 8 and s["totals"]["findings"] >= 1
    assert "clusters" in api.get("/api/clusters").json()
    tr = api.get("/api/trends", params={"entity_id": "E1"}).json()["weeks"]
    assert tr and all(w["entity_id"] == "E1" for w in tr)
    q = api.get("/api/review-queue").json()
    assert q["items"][0]["entity_id"] == "E6" and q["items"][0]["record_type"] == "asset"
    no_spot = api.get("/api/review-queue", params={"include_spot_checks": False}).json()
    assert all(i["finding_type"] != "spot_check" for i in no_spot["items"])


def test_reports(api):
    r = api.get("/api/reports/findings.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "silent_critical_assets" in r.text
    pdf = api.get("/api/reports/summary.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    epdf = api.get("/api/reports/entity/E6.pdf")
    assert epdf.status_code == 200 and epdf.content[:4] == b"%PDF"


def _zip_upload(tables: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, df in tables.items():
            z.writestr(f"{k}.csv", df.to_csv(index=False))
    return buf.getvalue()


def test_upload_and_rerun(tmp_path):
    t = world(n=8, alerts_per=60, seed=3)
    with client(tmp_path / "up.duckdb") as c:
        assert c.get("/api/entities").status_code == 404  # nothing analysed yet
        r = c.post("/api/ingest", files={"files": ("export.zip", _zip_upload(t), "application/zip")})
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["entity_ids"]) == 8 and body["analysis_run_id"]
        assert len(c.get("/api/entities").json()["entities"]) == 8
        # separate table files in one request
        extra = {"alerts": pd.DataFrame([{"alert_id": "X1", "entity_id": "E0", "ts": "2026-08-01T00:00:00Z",
                                           "category": "recon", "severity": "low"}])}
        r = c.post("/api/ingest", params={"analyse": False},
                   files=[("files", ("alerts.csv", extra["alerts"].to_csv(index=False), "text/csv"))])
        assert r.status_code == 200 and r.json()["row_counts"] == {"alerts": 1}
        run = c.post("/api/analysis/run", json={"params": {"z_min": 4}}).json()
        assert run["run_id"] and not run["detector_errors"]
        assert c.get(f"/api/runs/{run['run_id']}").json()["params"]["z_min"] == 4


def test_upload_validation_errors(tmp_path):
    t = world(n=2, alerts_per=10)
    t["alerts"].loc[0, "severity"] = "urgent"
    with client(tmp_path / "bad.duckdb") as c:
        r = c.post("/api/ingest", files={"files": ("export.zip", _zip_upload(t), "application/zip")})
        assert r.status_code == 422
        assert any("invalid value" in e for e in r.json()["errors"])
        r = c.post("/api/ingest", files={"files": ("notes.txt", b"hello", "text/plain")})
        assert r.status_code == 415


def test_read_only_mode(db_path):
    with client(db_path, read_only=True) as c:
        assert c.post("/api/analysis/run", json={}).status_code == 403
        assert c.post("/api/ingest", files={"files": ("a.zip", b"x", "application/zip")}).status_code == 403
        assert c.get("/api/entities").status_code == 200


def test_serves_built_frontend(db_path, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("nope")
    s = Settings()
    s.db_path, s.frontend_dir = str(db_path), str(dist)
    with TestClient(create_app(s)) as c:
        assert c.get("/").text == "<html>app</html>"
        assert c.get("/entities/E1").text == "<html>app</html>"  # SPA route falls back to index
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert "nope" not in c.get("/../secret.txt").text  # no escape from the dist folder
        assert c.get("/api/health").json()["status"] == "ok"  # API still wins


def test_summary_pie_data_and_filter(api):
    s = api.get("/api/summary").json()
    assert {"by_severity", "by_category", "alert_severity", "alert_category", "bands"} <= s.keys()
    assert sum(x["n"] for x in s["alert_severity"]) == s["totals"]["alerts"]
    one = api.get("/api/summary", params={"entity_id": "E6"}).json()
    assert one["totals"]["entities"] == 1 and one["entity_ids"] == ["E6"]
    assert [x["severity"] for x in one["by_severity"]] and all(b["n"] == 1 for b in one["bands"])
    assert len(one["alert_category"]) <= 7


def test_upload_any_alert_csv(tmp_path):
    csv = ("Timestamp,Severity,Alert Title,Host\n"
           "2026-06-01 10:00,Informational,Port scan,web01\n"
           "2026-06-01 11:00,High,Malware,pc22\n")
    with client(tmp_path / "generic.duckdb") as c:
        r = c.post("/api/ingest", params={"entity_name": "My SOC"},
                   files=[("files", ("my_alerts.csv", csv, "text/csv"))])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["entity_ids"] == ["MY-SOC"] and body["analysis_run_id"]
        assert any(w.startswith("auto-mapping:") for w in body["warnings"])
        s = c.get("/api/summary", params={"entity_id": "MY-SOC"}).json()
        assert s["totals"]["alerts"] == 2


def test_public_demo_keeps_only_recent_uploads(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCASSESS_KEEP_UPLOADS", "2")
    s = Settings()
    s.db_path = str(tmp_path / "demo.duckdb")
    with TestClient(create_app(s)) as c:
        for i in range(4):
            csv = f"Timestamp,Severity\n2026-06-0{i + 1} 10:00,High\n"
            r = c.post("/api/ingest", params={"entity_name": f"Org {i}", "analyse": False},
                       files=[("files", (f"o{i}.csv", csv, "text/csv"))])
            assert r.status_code == 200, r.text
        assert c.post("/api/analysis/run", json={}).status_code == 200
        ids = {e["entity_id"] for e in c.get("/api/entities").json()["entities"]}
        assert ids == {"ORG-2", "ORG-3"}


def test_health_never_blocks_during_analysis(db_path):
    import threading
    import time

    with client(db_path) as c:
        c.get("/api/health")  # fill the cache
        db = c.app.state.db
        held = threading.Event()
        release = threading.Event()

        def hold():
            with db.lock:
                held.set()
                release.wait(10)

        t = threading.Thread(target=hold)
        t.start()
        held.wait(5)
        t0 = time.perf_counter()
        h = c.get("/api/health").json()
        release.set()
        t.join()
        assert time.perf_counter() - t0 < 1 and h["busy"] is True and h["entities"] == 8
