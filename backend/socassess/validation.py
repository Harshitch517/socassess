"""Validate the engine against planted ground truth, and compare with manual random sampling.

Definitions
-----------
* A *weakness* is one (entity, type) pair planted by the generator.
* Detection: a finding of the same type on the same entity. Finding types the generator never
  plants (sla_breach, operational_anomaly) are not scored for precision/recall but are counted as
  false alarms when they land on a healthy entity.
* Evidence precision/recall: overlap between a finding's evidence ids and the planted record ids
  (missing_categories compares the category lists).
* Review baseline: a supervisor reviews randomly sampled case records (stratified: the same number per
  entity, as in a typical audit; or uniform over all cases). A weakness counts as *confirmed* when a
  reviewed record is one of its planted evidence records. Weaknesses with no case records
  (silent assets, missing categories, low activity, uncased alerts) cannot be found this way. That
  is the point of negative-space analytics, so the baseline is reported as is.
* Tool: the supervisor walks the review queue in priority order (spot-checks excluded). A weakness
  is confirmed when a reviewed item belongs to its finding and is planted evidence, or is a
  finding-level item (records that are absent by nature).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SCORED_EXTRA = {"sla_breach", "operational_anomaly"}


def planted_pairs(truth: dict) -> dict[tuple[str, str], dict]:
    return {(e, w["type"]): w for e, g in truth["entities"].items() for w in g["weaknesses"]}


def evaluate(findings: pd.DataFrame, scores: pd.DataFrame, truth: dict) -> dict:
    planted = planted_pairs(truth)
    gt_types = {t for _, t in planted}
    synth = set(truth["entities"])
    healthy = {e for e, g in truth["entities"].items() if g["healthy"]}
    f = findings[findings.entity_id.isin(synth)]
    scored = f[f.type.isin(gt_types)]
    detected = set(zip(scored.entity_id, scored.type, strict=True))
    tp, fp, fn = detected & planted.keys(), detected - planted.keys(), planted.keys() - detected

    per_type = []
    for t in sorted(gt_types):
        p = {k for k in planted if k[1] == t}
        d = {k for k in detected if k[1] == t}
        per_type.append({"type": t, "planted": len(p), "detected": len(d & p), "false_positive": len(d - p),
                         "precision": len(d & p) / len(d) if d else None, "recall": len(d & p) / len(p)})

    evidence = []
    for e, t in sorted(tp):
        w = planted[(e, t)]
        row = scored[(scored.entity_id == e) & (scored.type == t)].iloc[0]
        if t == "missing_categories":
            got, want = set(row.metric_values.get("missing", [])), set(w.get("categories", []))
        else:
            got, want = set(row.evidence_ids), set(w["evidence_ids"])
        if not want:
            continue
        hit = len(got & want)
        evidence.append({"entity_id": e, "type": t, "found": len(got), "planted": len(want), "overlap": hit,
                         "precision": hit / len(got) if got else 0.0, "recall": hit / len(want)})

    s = scores[scores.entity_id.isin(synth)].set_index("entity_id")
    weak = [e for e in synth if e not in healthy]
    rs = s.risk_score
    pairs = [(rs[w] > rs[h]) + 0.5 * (rs[w] == rs[h]) for w in weak for h in healthy]
    auc = float(np.mean(pairs)) if pairs else None  # P(weak entity scores above a healthy one)
    flagged = set(s.index[s.risk_score > 0])
    alarms = f[f.entity_id.isin(healthy)]
    ev = pd.DataFrame(evidence)
    extra_on_weak = int((f.type.isin(SCORED_EXTRA) & ~f.entity_id.isin(healthy)).sum())
    return {
        "weakness": {"planted": len(planted), "tp": len(tp), "fp": len(fp), "fn": len(fn),
                     "precision": len(tp) / (len(tp) + len(fp)) if tp or fp else None,
                     "recall": len(tp) / len(planted), "missed": sorted(fn), "spurious": sorted(fp)},
        "per_type": per_type,
        "evidence": evidence,
        "evidence_micro": {
            "precision": float(ev.overlap.sum() / ev.found.sum()) if len(ev) else None,
            "recall": float(ev.overlap.sum() / ev.planted.sum()) if len(ev) else None},
        "entities": {"weak": len(weak), "healthy": len(healthy), "auc_risk_score": auc,
                     "weak_flagged": len(flagged & set(weak)), "healthy_flagged": len(flagged & healthy),
                     "healthy_false_alarms": alarms[["entity_id", "type"]].to_dict("records"),
                     "extra_type_findings_on_weak": extra_on_weak},
    }


def _confirmable_cases(truth: dict, case_ids: set[str]) -> dict[tuple[str, str], set[str]]:
    """Planted evidence that a case reviewer could actually come across."""
    return {k: set(w["evidence_ids"]) & case_ids for k, w in planted_pairs(truth).items()}


def random_review_curve(cases: pd.DataFrame, truth: dict, budgets: list[int], runs: int = 200,
                        stratified: bool = True, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    synth = set(truth["entities"])
    c = cases[cases.entity_id.isin(synth)]
    reachable = _confirmable_cases(truth, set(c.case_id))
    by_entity = {e: g.case_id.to_numpy() for e, g in c.groupby("entity_id")}
    all_ids = c.case_id.to_numpy()
    n_planted = len(reachable)
    rows = []
    for b in budgets:
        found = []
        for _ in range(runs):
            if stratified:
                per = max(1, b // len(by_entity))
                sample = set(np.concatenate([rng.choice(ids, size=min(per, len(ids)), replace=False)
                                             for ids in by_entity.values()]))
            else:
                sample = set(rng.choice(all_ids, size=min(b, len(all_ids)), replace=False))
            found.append(sum(1 for ev in reachable.values() if ev & sample))
        reviewed = (max(1, b // len(by_entity)) * len(by_entity)) if stratified else b
        rows.append({"records_reviewed": reviewed, "confirmed_mean": float(np.mean(found)),
                     "confirmed_p10": float(np.percentile(found, 10)), "confirmed_p90": float(np.percentile(found, 90)),
                     "recall_mean": float(np.mean(found)) / n_planted})
    return pd.DataFrame(rows).drop_duplicates("records_reviewed")


def tool_review_curve(queue: pd.DataFrame, truth: dict) -> pd.DataFrame:
    planted = planted_pairs(truth)
    q = queue[(queue.finding_type != "spot_check") & queue.entity_id.isin(set(truth["entities"]))].sort_values("rank")
    confirmed: set = set()
    rows = [{"records_reviewed": 0, "confirmed": 0, "recall": 0.0}]
    for i, item in enumerate(q.itertuples(), start=1):
        key = (item.entity_id, item.finding_type)
        if key in planted and key not in confirmed:
            w = planted[key]
            evidence = set(w["evidence_ids"])
            if item.record_type == "finding" or item.record_id in evidence:
                confirmed.add(key)
        rows.append({"records_reviewed": i, "confirmed": len(confirmed), "recall": len(confirmed) / len(planted)})
    return pd.DataFrame(rows)
