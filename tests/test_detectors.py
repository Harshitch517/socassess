import numpy as np
import pandas as pd
from conftest import load

from socassess.analytics import execution as ex
from socassess.analytics import negative_space as ns
from socassess.analytics.engine import DETECTORS

TEMPLATE = "Alert reviewed. No malicious activity observed. Closing as false positive."


def only(findings, entity, type_):
    assert [(f.entity_id, f.type) for f in findings] == [(entity, type_)], \
        [(f.entity_id, f.type, f.title) for f in findings]
    f = findings[0]
    assert f.rationale and f.metric_values and f.severity in {"low", "medium", "high", "critical"}
    return f


def test_clean_world_has_no_findings(tables, params):
    _, d = load(tables)
    for det in DETECTORS:
        assert det(d, params) == [], det.__name__


def test_fast_closure(tables, params):
    c = tables["cases"]
    al = tables["alerts"].set_index("case_id").severity
    hit = (c.entity_id == "E1") & c.case_id.map(al).isin(["high", "critical"]) & (c.index % 2 == 0)
    c.loc[hit, "closed_at"] = c.loc[hit, "opened_at"] + pd.Timedelta(minutes=2)
    _, d = load(tables)
    f = only(ex.fast_closure(d, params), "E1", "fast_closure")
    assert set(f.evidence_ids) == set(c.loc[hit, "case_id"])
    assert f.metric_values["median_minutes"] == 2.0


def test_critical_no_escalation(tables, params):
    c = tables["cases"]
    sev = c.case_id.map(tables["alerts"].set_index("case_id").severity)
    hit = (c.entity_id == "E2") & (sev == "critical") & (c.disposition == "true_positive")
    c.loc[hit, "escalated"] = False
    tables["escalations"] = tables["escalations"][~tables["escalations"].case_id.isin(c.loc[hit, "case_id"])]
    _, d = load(tables)
    params["critical_no_escalation"]["min_cases"] = 5  # the test world has ~10 critical TPs per entity
    f = only(ex.critical_no_escalation(d, params), "E2", "critical_no_escalation")
    assert set(f.evidence_ids) == set(c.loc[hit, "case_id"])


def test_near_duplicate_groups():
    texts = pd.Series([TEMPLATE, TEMPLATE.lower(), TEMPLATE.replace(".", ""), TEMPLATE + "  ",
                       "Alert reviewed. No malicious activity observed. Closing as benign.",
                       "Confirmed ransomware on host 12, isolated and reimaged.", "Phish reported by user."])
    g = ex.near_duplicate_groups(texts, 0.92)
    assert len(set(g[:4])) == 1
    assert g[5] != g[0] and g[6] != g[0] and g[5] != g[6]


def test_template_notes(tables, params):
    c = tables["cases"]
    hit = (c.entity_id == "E3") & c.assignee.isin(["E3.an0", "E3.an1"])
    variants = [TEMPLATE, TEMPLATE.lower(), TEMPLATE.rstrip(".")]
    c.loc[hit, "notes"] = [variants[i % 3] for i in range(int(hit.sum()))]
    _, d = load(tables)
    f = only(ex.template_notes(d, params), "E3", "template_notes")
    assert set(f.evidence_ids) == set(c.loc[hit, "case_id"])
    assert set(f.metric_values["by_analyst"]) == {"E3.an0", "E3.an1"}


def _add_repeats(tables, eid, n, remediate_at=None):
    rows_a, rows_c = [], []
    for i in range(n):
        aid, cid = f"{eid}-RP{i:03d}", f"{eid}-RC{i:03d}"
        ts = pd.Timestamp("2026-06-02", tz="UTC") + pd.Timedelta(days=2 * i)
        rows_a.append({"alert_id": aid, "entity_id": eid, "asset_id": f"{eid}-A05", "ts": ts,
                       "category": "malware", "severity": "high", "rule_name": "Same malware rule", "case_id": cid})
        rows_c.append({"case_id": cid, "entity_id": eid, "alert_id": aid, "assignee": "x", "opened_at": ts,
                       "closed_at": ts + pd.Timedelta(hours=2), "sla_deadline": ts + pd.Timedelta(hours=8),
                       "status": "closed", "disposition": "false_positive", "escalated": False,
                       "remediation": "patch applied" if i == remediate_at else None, "notes": f"seen {i}"})
    tables["alerts"] = pd.concat([tables["alerts"], pd.DataFrame(rows_a)], ignore_index=True)
    tables["cases"] = pd.concat([tables["cases"], pd.DataFrame(rows_c)], ignore_index=True)
    return [r["case_id"] for r in rows_c]


def test_repeated_no_remediation(tables, params):
    ids = _add_repeats(tables, "E4", 15)
    _, d = load(tables)
    f = only(ex.repeated_no_remediation(d, params), "E4", "repeated_no_remediation")
    assert set(ids) <= set(f.evidence_ids)
    assert f.metric_values["pairs"][0]["asset_id"] == "E4-A05"


def test_repeated_with_fix_midway_is_not_flagged(tables, params):
    _add_repeats(tables, "E4", 15, remediate_at=7)  # two stretches of 8 and 7 alerts
    _, d = load(tables)
    assert ex.repeated_no_remediation(d, params) == []


def test_sla_gaming(tables, params):
    c = tables["cases"]
    hit = (c.entity_id == "E5") & (c.index % 3 != 0)
    window = c.loc[hit, "sla_deadline"] - c.loc[hit, "opened_at"]
    c.loc[hit, "closed_at"] = c.loc[hit, "sla_deadline"] - window * 0.02
    _, d = load(tables)
    f = only(ex.sla_gaming(d, params), "E5", "sla_gaming")
    assert set(c.loc[hit, "case_id"]) <= set(f.evidence_ids)
    assert f.metric_values["bunching_ratio"] > 3


def test_sla_breach(tables, params):
    c = tables["cases"]
    hit = (c.entity_id == "E6") & (c.index % 2 == 0)
    c.loc[hit, "closed_at"] = c.loc[hit, "sla_deadline"] + pd.Timedelta(hours=5)
    _, d = load(tables)
    only(ex.sla_breach(d, params), "E6", "sla_breach")


def test_silent_critical_assets(tables, params):
    t = tables["telemetry"]
    t.loc[t.asset_id.isin(["E6-A00", "E6-A01"]), "event_count"] = 0
    _, d = load(tables)
    f = only(ns.silent_critical_assets(d, params), "E6", "silent_critical_assets")
    assert sorted(f.evidence_ids) == ["E6-A00", "E6-A01"]


def test_critical_asset_without_any_telemetry(tables, params):
    t = tables["telemetry"]
    tables["telemetry"] = t[t.asset_id != "E6-A02"]
    _, d = load(tables)
    f = only(ns.silent_critical_assets(d, params), "E6", "silent_critical_assets")
    assert f.evidence_ids == ["E6-A02"]


def test_missing_categories(tables, params):
    a = tables["alerts"]
    drop = (a.entity_id == "E7") & (a.category == "lateral_movement")
    tables["alerts"] = a[~drop]
    tables["cases"] = tables["cases"][~tables["cases"].alert_id.isin(a.loc[drop, "alert_id"])]
    tables["escalations"] = tables["escalations"][tables["escalations"].case_id.isin(tables["cases"].case_id)]
    _, d = load(tables)
    f = only(ns.missing_categories(d, params), "E7", "missing_categories")
    assert f.metric_values["missing"] == ["lateral_movement"] and f.severity == "high"


def test_missing_records(tables, params):
    a, c = tables["alerts"], tables["cases"]
    uncased = a[(a.entity_id == "E0") & a.severity.isin(["high", "critical"])].alert_id[:10]
    a.loc[a.alert_id.isin(uncased), "case_id"] = None
    tables["cases"] = c[~c.alert_id.isin(uncased)]
    e = tables["escalations"]
    e = e[e.case_id.isin(tables["cases"].case_id)]
    gone = e[e.entity_id == "E0"].case_id[:5]
    tables["escalations"] = e[~e.case_id.isin(gone)]
    _, d = load(tables)
    f = only(ns.missing_records(d, params), "E0", "missing_records")
    assert set(uncased) | set(gone) == set(f.evidence_ids)


def test_low_activity(tables, params):
    a = tables["alerts"]
    keep = (a.entity_id != "E1") | (np.arange(len(a)) % 10 == 0)
    tables["alerts"] = a[keep]
    tables["cases"] = tables["cases"][tables["cases"].alert_id.isin(tables["alerts"].alert_id)]
    tables["escalations"] = tables["escalations"][tables["escalations"].case_id.isin(tables["cases"].case_id)]
    _, d = load(tables)
    f = only(ns.low_activity(d, params), "E1", "low_activity")
    assert f.metric_values["ratio"] < 0.2
    assert "logs are arriving" in f.rationale  # telemetry is normal, so detection is the gap


def test_entity_without_cases_is_not_judged_on_case_detectors(tables, params):
    for t in ("cases", "escalations"):
        tables[t] = tables[t][tables[t].entity_id != "E2"]
    tables["alerts"].loc[tables["alerts"].entity_id == "E2", "case_id"] = None
    _, d = load(tables)
    for det in (ns.missing_records, ex.fast_closure, ex.template_notes):
        assert all(f.entity_id != "E2" for f in det(d, params))
