"""Run all analytics and persist the results with an audit record."""

from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

import socassess
from socassess.analytics import benchmark, execution, negative_space, scoring
from socassess.analytics.clustering import cluster_patterns
from socassess.analytics.common import Data, Finding, load_data
from socassess.analytics.params import DEFAULT_PARAMS

DETECTORS = execution.DETECTORS + negative_space.DETECTORS


@dataclass
class AnalysisResult:
    run_id: str
    started_at: datetime
    duration_s: float
    input_hash: str
    params: dict
    code_version: str
    findings: list[Finding]
    scores: pd.DataFrame
    metrics: pd.DataFrame
    benchmarks: pd.DataFrame
    patterns: pd.DataFrame
    clusters: pd.DataFrame
    queue: pd.DataFrame
    trends: pd.DataFrame
    detector_errors: dict


def merge_params(overrides: dict | None) -> dict:
    p = copy.deepcopy(DEFAULT_PARAMS)
    for k, v in (overrides or {}).items():
        if isinstance(v, dict) and isinstance(p.get(k), dict):
            p[k].update(v)
        else:
            p[k] = v
    return p


def code_version() -> str:
    h = hashlib.sha256()
    for f in sorted(Path(__file__).parent.glob("*.py")):
        h.update(f.read_bytes())
    return f"{socassess.__version__}+{h.hexdigest()[:10]}"


def input_hash(con: duckdb.DuckDBPyConnection) -> str:
    """Fingerprint of what is in the store: every ingested input's SHA-256 plus, per table, the row
    count and an order-independent XOR of row hashes (so any changed value changes the hash)."""
    shas = [r[0] for r in con.execute("SELECT input_sha256 FROM ingest_runs ORDER BY 1").fetchall()]
    content = {t: [str(v) for v in con.execute(f"SELECT count(*), bit_xor(hash(t)) FROM {t} AS t").fetchone()]
               for t in ("entities", "assets", "alerts", "cases", "escalations", "telemetry")}
    return hashlib.sha256(json.dumps([shas, content]).encode()).hexdigest()


def analyse(d: Data, params: dict) -> tuple[list[Finding], dict]:
    findings, errors = [], {}
    for det in DETECTORS:
        try:
            findings.extend(det(d, params))
        except Exception as e:  # one broken detector must not hide the others' results
            errors[det.__name__] = f"{type(e).__name__}: {e}"
    return findings, errors


def run_analysis(con: duckdb.DuckDBPyConnection, params: dict | None = None,
                 entity_ids: list[str] | None = None) -> AnalysisResult:
    p = merge_params(params)
    t0 = time.perf_counter()
    started = datetime.now(UTC)
    d = load_data(con, entity_ids)
    findings, errors = analyse(d, p)
    metrics = benchmark.entity_metrics(d)
    bench = benchmark.benchmark(d, metrics)
    anomaly_scores, anomaly_findings = benchmark.anomalies(d, metrics, bench, p)
    findings += anomaly_findings
    scores = scoring.risk_scores(d, findings, p, anomaly_scores)
    queue = scoring.review_queue(d, findings, scores, p)
    patterns, clusters = cluster_patterns(d, p)
    trends = benchmark.weekly_trends(d)
    return AnalysisResult(uuid.uuid4().hex[:12], started, round(time.perf_counter() - t0, 2),
                          input_hash(con), p, code_version(), findings, scores, metrics, bench,
                          patterns, clusters, queue, trends, errors)


# ---------------------------------------------------------------- persistence

RESULT_DDL = """
CREATE TABLE IF NOT EXISTS analysis_runs (
  run_id VARCHAR PRIMARY KEY, started_at TIMESTAMPTZ, duration_s DOUBLE, input_hash VARCHAR,
  params JSON, params_hash VARCHAR, code_version VARCHAR, entity_ids VARCHAR[], n_findings INTEGER,
  detector_errors JSON, trigger VARCHAR);
CREATE TABLE IF NOT EXISTS findings (
  run_id VARCHAR, finding_id VARCHAR, entity_id VARCHAR, type VARCHAR, category VARCHAR,
  severity VARCHAR, title VARCHAR, rationale VARCHAR, evidence_kind VARCHAR, evidence_ids VARCHAR[],
  n_evidence INTEGER, metric_values JSON, detector VARCHAR, points DOUBLE);
CREATE TABLE IF NOT EXISTS entity_scores (
  run_id VARCHAR, entity_id VARCHAR, name VARCHAR, sector VARCHAR, size VARCHAR, source VARCHAR,
  risk_score DOUBLE, raw_points DOUBLE, band VARCHAR, rank INTEGER, n_findings INTEGER,
  has_case_data BOOLEAN, anomaly_score DOUBLE, breakdown JSON);
CREATE TABLE IF NOT EXISTS entity_benchmarks (
  run_id VARCHAR, entity_id VARCHAR, metric VARCHAR, description VARCHAR, direction INTEGER,
  value DOUBLE, peer_median_all DOUBLE, peer_median_size DOUBLE, size_peers VARCHAR[],
  percentile DOUBLE, z DOUBLE, n_peers INTEGER);
CREATE TABLE IF NOT EXISTS review_queue (
  run_id VARCHAR, rank INTEGER, entity_id VARCHAR, finding_id VARCHAR, finding_type VARCHAR,
  severity VARCHAR, record_type VARCHAR, record_id VARCHAR, reason VARCHAR, priority DOUBLE);
CREATE TABLE IF NOT EXISTS pattern_clusters (
  run_id VARCHAR, cluster_id INTEGER, label VARCHAR, patterns INTEGER, alerts BIGINT,
  n_entities INTEGER, entities VARCHAR[], cross_entity BOOLEAN, main_category VARCHAR,
  categories JSON, top_rules JSON, profile JSON);
CREATE TABLE IF NOT EXISTS alert_patterns (
  run_id VARCHAR, entity_id VARCHAR, rule_name VARCHAR, category VARCHAR, alerts BIGINT,
  assets BIGINT, active_days BIGINT, after_hours_share DOUBLE, severity_mean DOUBLE,
  burstiness DOUBLE, asset_spread DOUBLE, first_seen TIMESTAMPTZ, last_seen TIMESTAMPTZ,
  cluster_id INTEGER);
CREATE TABLE IF NOT EXISTS weekly_trends (
  run_id VARCHAR, entity_id VARCHAR, week VARCHAR, alerts BIGINT, high_critical BIGINT,
  cases_closed DOUBLE, median_ttc_hours DOUBLE, fast_closures DOUBLE, sla_breaches DOUBLE,
  escalated DOUBLE);
"""


def _insert(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    cols = [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]
    frame = df.reindex(columns=cols)  # noqa: F841 - used by name in SQL
    con.execute(f"INSERT INTO {table} SELECT * FROM frame")


def _json(v) -> str:
    return json.dumps(v, default=str)


def persist(con: duckdb.DuckDBPyConnection, res: AnalysisResult, trigger: str = "cli",
            entity_ids: list[str] | None = None) -> None:
    con.execute(RESULT_DDL)
    p_json = _json(res.params)
    fd = pd.DataFrame([f.to_dict() for f in res.findings])
    if not fd.empty:
        fd["points"] = [scoring.finding_points(f, res.params) for f in res.findings]
        fd["n_evidence"] = fd.evidence_ids.map(len)
        fd["metric_values"] = fd.metric_values.map(_json)
    sc = res.scores.copy()
    sc["breakdown"] = sc.breakdown.map(_json)
    cl = res.clusters.copy()
    for c in ("categories", "top_rules", "profile"):
        if c in cl:
            cl[c] = cl[c].map(_json)
    con.execute("BEGIN TRANSACTION")
    try:
        for name, df in (("findings", fd), ("entity_scores", sc), ("entity_benchmarks", res.benchmarks),
                         ("review_queue", res.queue), ("pattern_clusters", cl),
                         ("alert_patterns", res.patterns), ("weekly_trends", res.trends)):
            _insert(con, name, df.assign(run_id=res.run_id) if not df.empty else df)
        con.execute("INSERT INTO analysis_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
            res.run_id, res.started_at, res.duration_s, res.input_hash, p_json,
            hashlib.sha256(p_json.encode()).hexdigest()[:16], res.code_version, entity_ids or [],
            len(res.findings), _json(res.detector_errors), trigger])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def latest_run_id(con: duckdb.DuckDBPyConnection) -> str | None:
    try:
        row = con.execute("SELECT run_id FROM analysis_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    except duckdb.CatalogException:
        return None
    return row[0] if row else None
