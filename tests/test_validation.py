import pandas as pd

from socassess.validation import evaluate, random_review_curve, tool_review_curve

TRUTH = {"entities": {
    "A": {"healthy": False, "weaknesses": [
        {"type": "fast_closure", "evidence_ids": ["A-1", "A-2", "A-3", "A-4"]},
        {"type": "low_activity", "evidence_ids": []}]},
    "B": {"healthy": False, "weaknesses": [{"type": "missing_categories", "evidence_ids": [],
                                             "categories": ["ics_anomaly"]}]},
    "C": {"healthy": True, "weaknesses": []},
    "D": {"healthy": True, "weaknesses": []},
}}


def F(e, t, ev=(), mv=None):
    return {"entity_id": e, "type": t, "evidence_ids": list(ev), "metric_values": mv or {}}


def test_evaluate_counts_and_evidence():
    findings = pd.DataFrame([
        F("A", "fast_closure", ["A-1", "A-2", "A-3", "A-9"]),   # 3 of 4 planted + 1 extra
        F("B", "missing_categories", mv={"missing": ["ics_anomaly"]}),
        F("C", "fast_closure", ["C-1"]),                          # wrong entity: FP + healthy alarm
        F("A", "operational_anomaly"),                            # unscored type on a weak entity
    ])
    scores = pd.DataFrame({"entity_id": list("ABCD"), "risk_score": [30, 10, 15, 0]})
    r = evaluate(findings, scores, TRUTH)
    w = r["weakness"]
    assert (w["tp"], w["fp"], w["fn"]) == (2, 1, 1)
    assert w["missed"] == [("A", "low_activity")] and w["spurious"] == [("C", "fast_closure")]
    fc = next(e for e in r["evidence"] if e["type"] == "fast_closure")
    assert (fc["precision"], fc["recall"]) == (0.75, 0.75)
    mc = next(e for e in r["evidence"] if e["type"] == "missing_categories")
    assert mc["recall"] == 1.0
    ent = r["entities"]
    assert ent["healthy_flagged"] == 1 and ent["weak_flagged"] == 2
    assert ent["auc_risk_score"] == 0.75  # A beats C and D; B beats D only
    assert ent["extra_type_findings_on_weak"] == 1


def test_tool_curve_requires_real_evidence():
    queue = pd.DataFrame([
        {"rank": 1, "entity_id": "A", "finding_type": "fast_closure", "record_type": "case", "record_id": "A-9"},
        {"rank": 2, "entity_id": "A", "finding_type": "fast_closure", "record_type": "case", "record_id": "A-1"},
        {"rank": 3, "entity_id": "B", "finding_type": "missing_categories", "record_type": "finding", "record_id": "x"},
        {"rank": 4, "entity_id": "C", "finding_type": "spot_check", "record_type": "case", "record_id": "C-1"},
    ])
    c = tool_review_curve(queue, TRUTH)
    assert c.confirmed.tolist() == [0, 0, 1, 2]  # A-9 is not planted evidence; spot-check excluded


def test_random_curve_cannot_reach_negative_space():
    cases = pd.DataFrame({"case_id": [f"A-{i}" for i in range(1, 11)] + ["C-1", "D-1"],
                          "entity_id": ["A"] * 10 + ["C", "D"]})
    c = random_review_curve(cases, TRUTH, [3, 30], runs=50, stratified=False)
    # only fast_closure has case evidence: recall can never exceed 1 of 3 planted weaknesses
    assert c.recall_mean.max() <= 1 / 3 + 1e-9
    assert c.iloc[-1].confirmed_mean == 1.0  # reviewing every case finds it
