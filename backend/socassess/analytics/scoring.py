"""Transparent entity risk score and review prioritisation.

Risk score = min(100, sum over findings of weight[type] x severity_multiplier[severity]).
Risk band = the score's band, raised to the entity's worst finding severity (one serious finding
means at least a "high" band, so the band never contradicts the warnings shown).
Every point is traceable to one finding; the breakdown is stored with the score.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from socassess.analytics.common import SEV_RANK, Data, Finding

BANDS = [(50, "critical"), (30, "high"), (10, "medium"), (0, "low")]


def finding_points(f: Finding, p: dict) -> float:
    return float(p["risk_weights"].get(f.type, 5) * p["severity_multiplier"][f.severity])


def band(score: float) -> str:
    return next(b for thr, b in BANDS if score >= thr)


def risk_scores(d: Data, findings: list[Finding], p: dict, anomaly: pd.Series) -> pd.DataFrame:
    rows = []
    for e in d.entities.itertuples():
        fs = [f for f in findings if f.entity_id == e.entity_id]
        breakdown = sorted(({
            "finding_id": f.finding_id, "type": f.type, "severity": f.severity, "title": f.title,
            "weight": p["risk_weights"].get(f.type, 5), "multiplier": p["severity_multiplier"][f.severity],
            "points": finding_points(f, p)} for f in fs), key=lambda b: -b["points"])
        raw = sum(b["points"] for b in breakdown)
        score = min(100.0, raw)
        a = anomaly.get(e.entity_id, np.nan)
        rows.append({"entity_id": e.entity_id, "name": e.name, "sector": e.sector, "size": e.size,
                     "source": e.source, "risk_score": round(score, 2), "raw_points": round(raw, 2),
                     "band": max([band(score)] + [f.severity for f in fs], key=SEV_RANK.get),
                     "n_findings": len(fs),
                     "has_case_data": e.entity_id in d.with_cases(),
                     "anomaly_score": None if pd.isna(a) else round(float(a), 3),
                     "breakdown": breakdown})
    df = pd.DataFrame(rows).sort_values(["risk_score", "n_findings", "entity_id"],
                                        ascending=[False, False, True]).reset_index(drop=True)
    df["rank"] = np.arange(1, len(df) + 1)
    return df


def _rank_cases(d: Data, ids: list[str]) -> list[str]:
    c = d.cases[d.cases.case_id.isin(ids)].copy()
    c["sev"] = c.severity.map(SEV_RANK).fillna(0)
    c["crit"] = (c.asset_criticality == "critical").astype(int)
    return c.sort_values(["sev", "crit", "ttc_min"], ascending=[False, False, True]).case_id.tolist()


def review_queue(d: Data, findings: list[Finding], scores: pd.DataFrame, p: dict) -> pd.DataFrame:
    """Ranked list of concrete records for a supervisor to review by hand.

    For each finding: the k most telling evidence records. For each entity with case data:
    a seeded random spot-check of high/critical cases not already queued, as a control sample.
    """
    k = p["review_samples_per_finding"]
    rng = np.random.default_rng(0)
    entity_score = dict(zip(scores.entity_id, scores.risk_score, strict=True))
    items = []
    for f in findings:
        pts = finding_points(f, p)
        base = {"entity_id": f.entity_id, "finding_id": f.finding_id, "finding_type": f.type,
                "severity": f.severity}
        if f.evidence_kind == "case":
            picks = [("case", i) for i in _rank_cases(d, f.evidence_ids)[:k]]
        elif f.evidence_kind == "alert+case":
            alerts = [i for i in f.evidence_ids if "-AL" in i][: (k + 1) // 2]
            cases = [i for i in f.evidence_ids if "-AL" not in i][: k // 2]
            picks = [("alert", i) for i in alerts] + [("case", i) for i in cases]
        elif f.evidence_kind == "asset":
            picks = [("asset", i) for i in f.evidence_ids[:k]]
        else:
            picks = [("finding", f.finding_id)]
        for j, (kind, rid) in enumerate(picks):
            items.append(base | {"record_type": kind, "record_id": rid,
                                 "reason": f"Evidence for: {f.title}",
                                 "priority": round(pts + entity_score.get(f.entity_id, 0) / 10 - j * 0.01, 3)})
    queued = {i["record_id"] for i in items}
    for eid in sorted(d.with_cases()):
        pool = d.cases[(d.cases.entity_id == eid) & d.cases.severity.isin(["high", "critical"])
                       & ~d.cases.case_id.isin(queued)].case_id.to_numpy()
        if len(pool) == 0:
            continue
        for rid in rng.choice(pool, size=min(p["spot_check_samples"], len(pool)), replace=False):
            items.append({"entity_id": eid, "finding_id": None, "finding_type": "spot_check",
                          "severity": "low", "record_type": "case", "record_id": str(rid),
                          "reason": "Random spot-check of a high/critical case (control sample)",
                          "priority": round(entity_score.get(eid, 0) / 10, 3)})
    q = pd.DataFrame(items)
    if q.empty:
        return q
    q = q.sort_values(["priority", "entity_id"], ascending=[False, True]).reset_index(drop=True)
    q["rank"] = np.arange(1, len(q) + 1)
    return q
