import json

import pandas as pd
import pytest
from conftest import load

from socassess.analytics import benchmark, scoring
from socassess.analytics.clustering import cluster_patterns
from socassess.analytics.common import Finding, peer_z
from socassess.analytics.engine import latest_run_id, merge_params, persist, run_analysis


def mk(entity, type_, sev, kind="case", ids=("x",)):
    return Finding(entity, type_, "execution_gap", sev, f"{type_} title", "why", list(ids), kind, {"m": 1})


def test_peer_z_is_robust_to_one_outlier():
    s = pd.Series([0.01, 0.012, 0.011, 0.009, 0.5])
    z = peer_z(s, pd.Series(["a"] * 5), min_scale=0.001)
    assert z.iloc[-1] > 10 and z.iloc[:-1].abs().max() < 2


def test_risk_score_is_transparent(tables, params):
    _, d = load(tables)
    fs = [mk("E1", "critical_no_escalation", "critical"), mk("E1", "template_notes", "low"),
          mk("E2", "fast_closure", "high")]
    s = scoring.risk_scores(d, fs, params, pd.Series(dtype=float)).set_index("entity_id")
    assert s.at["E1", "risk_score"] == 25 * 1.0 + 10 * 0.25
    assert sum(b["points"] for b in s.at["E1", "breakdown"]) == s.at["E1", "risk_score"]
    assert s.at["E2", "risk_score"] == 15 * 0.75
    assert s.at["E0", "risk_score"] == 0 and s.at["E0", "band"] == "low"
    assert list(s.sort_values("rank").index[:2]) == ["E1", "E2"]


def test_risk_score_caps_at_100(tables, params):
    _, d = load(tables)
    fs = [mk("E1", "critical_no_escalation", "critical", ids=(str(i),)) for i in range(6)]
    fs = [Finding(f.entity_id, f.type, f.category, f.severity, f"t{i}", "", [], "none") for i, f in enumerate(fs)]
    s = scoring.risk_scores(d, fs, params, pd.Series(dtype=float)).set_index("entity_id")
    assert s.at["E1", "risk_score"] == 100 and s.at["E1", "raw_points"] == 150


def test_review_queue(tables, params):
    _, d = load(tables)
    ids = d.cases[d.cases.entity_id == "E1"].case_id[:20].tolist()
    fs = [mk("E1", "fast_closure", "high", ids=ids), mk("E3", "missing_categories", "medium", "none", ())]
    s = scoring.risk_scores(d, fs, params, pd.Series(dtype=float))
    q = scoring.review_queue(d, fs, s, params)
    ev = q[q.finding_type == "fast_closure"]
    assert len(ev) == params["review_samples_per_finding"] and set(ev.record_id) <= set(ids)
    assert (q[q.finding_type == "missing_categories"].record_type == "finding").all()
    spot = q[q.finding_type == "spot_check"]
    assert spot.entity_id.nunique() == 8 and not set(spot.record_id) & set(ev.record_id)
    assert q["rank"].is_unique and q.iloc[0].finding_type == "fast_closure"


def test_benchmark_and_metrics(tables):
    _, d = load(tables)
    m = benchmark.entity_metrics(d)
    assert m.loc["E0", "escalation_rate_crit_tp"] == 1.0
    assert m.loc["E0", "uncased_alert_share"] == 0.0
    b = benchmark.benchmark(d, m)
    assert b.percentile.between(0, 1).all()
    assert (b.n_peers == 7).all()


def test_clustering_runs(tables, params):
    _, d = load(tables)
    patterns, clusters = cluster_patterns(d, params)
    assert len(patterns) == 8 * 8  # rule index i % 2 is tied to category i % 8: 8 rules per entity
    assert {"cluster_id", "log_alerts", "asset_spread"} <= set(patterns.columns)
    if len(clusters):
        assert clusters.patterns.sum() == (patterns.cluster_id >= 0).sum()


def test_merge_params_is_deep_and_safe():
    p = merge_params({"fast_closure": {"min_rate": 0.5}, "z_min": 4})
    assert p["fast_closure"]["min_rate"] == 0.5 and p["fast_closure"]["max_minutes"]["high"] == 10
    assert merge_params(None)["fast_closure"]["min_rate"] == 0.05  # defaults untouched


@pytest.mark.parametrize("planted", [True, False])
def test_engine_end_to_end_and_audit(tables, planted):
    if planted:
        t = tables["telemetry"]
        t.loc[t.asset_id.isin(["E6-A00", "E6-A01"]), "event_count"] = 0
    con, _ = load(tables)
    res = run_analysis(con)
    assert not res.detector_errors
    types = {(f.entity_id, f.type) for f in res.findings}
    assert (("E6", "silent_critical_assets") in types) == planted
    persist(con, res, trigger="test")
    run = latest_run_id(con)
    assert run == res.run_id
    row = con.execute("SELECT input_hash, params, code_version, n_findings, trigger FROM analysis_runs").fetchone()
    assert len(row[0]) == 64 and json.loads(row[1])["z_min"] == 3.0 and row[4] == "test"
    assert row[3] == len(res.findings)
    n = con.execute("SELECT count(*) FROM entity_scores WHERE run_id = ?", [run]).fetchone()[0]
    assert n == 8
    # same data -> same input hash on a second run
    assert run_analysis(con).input_hash == res.input_hash


def test_input_hash_tracks_content():
    from conftest import world

    from socassess.analytics.engine import input_hash
    con, _ = load(world(n=3, alerts_per=50))
    h = input_hash(con)
    assert input_hash(con) == h
    con.execute("UPDATE alerts SET category = 'recon' WHERE alert_id = 'E0-AL00001'")
    assert input_hash(con) != h
