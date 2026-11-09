"""Execution-gap detectors: was the work that was done, done properly?"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
from scipy.sparse.csgraph import connected_components
from sklearn.feature_extraction.text import TfidfVectorizer

from socassess.analytics.common import Data, Finding, fmt_pct, grade, peer_median, peer_z, r


def _entity_rates(d: Data, df: pd.DataFrame, flag: str, min_scale: float) -> pd.DataFrame:
    """Per-entity n, k (flagged), rate, peer median and robust z within the same source."""
    g = df.groupby("entity_id")[flag].agg(n="size", k="sum").reset_index()
    g["rate"] = g.k / g.n
    g["source"] = g.entity_id.map(d.source_of())
    g["peer_median"] = peer_median(g.rate, g.source)
    g["z"] = peer_z(g.rate, g.source, min_scale)
    return g


def _flagged(g: pd.DataFrame, min_rate: float, z_min: float, min_n: int) -> pd.DataFrame:
    return g[(g.n >= min_n) & (g.rate >= min_rate) & (g.z >= z_min)]


def _closed(d: Data) -> pd.DataFrame:
    return d.cases[(d.cases.status == "closed") & d.cases.closed_at.notna()].copy()


def fast_closure(d: Data, p: dict) -> list[Finding]:
    cfg = p["fast_closure"]
    c = _closed(d)
    c = c[c.severity.isin(list(cfg["max_minutes"]))].copy()
    if c.empty:
        return []
    c["limit"] = c.severity.map(cfg["max_minutes"])
    c["fast"] = c.ttc_min < c["limit"]
    g = _entity_rates(d, c, "fast", cfg["min_scale"])
    out = []
    for row in _flagged(g, cfg["min_rate"], p["z_min"], p["min_cases"]).itertuples():
        ev = c[(c.entity_id == row.entity_id) & c.fast].sort_values("ttc_min")
        by_sev = ev.severity.value_counts().to_dict()
        med = float(ev.ttc_min.median())
        out.append(Finding(
            row.entity_id, "fast_closure", "execution_gap",
            grade(row.rate, [(0.30, "critical"), (0.15, "high")], "medium"),
            f"{int(row.k)} high/critical cases closed within minutes",
            (f"{fmt_pct(row.rate)} of closed high/critical cases ({int(row.k)} of {int(row.n)}) were closed "
             f"faster than a plausible investigation (critical < {cfg['max_minutes']['critical']} min, "
             f"high < {cfg['max_minutes']['high']} min); median {med:.1f} min. Peer median is "
             f"{fmt_pct(row.peer_median)} (robust z = {row.z:.1f})."),
            ev.case_id.tolist(), "case",
            {"rate": r(row.rate), "count": int(row.k), "cases_considered": int(row.n),
             "peer_median_rate": r(row.peer_median), "z": r(row.z, 2), "median_minutes": r(med, 2),
             "by_severity": {k: int(v) for k, v in by_sev.items()},
             "fp_or_benign_share": r(float(ev.disposition.isin(["false_positive", "benign"]).mean()))},
            "fast_closure"))
    return out


def critical_no_escalation(d: Data, p: dict) -> list[Finding]:
    cfg = p["critical_no_escalation"]
    c = _closed(d)
    c = c[(c.severity == "critical") & (c.disposition == "true_positive")].copy()
    if c.empty:
        return []
    c["not_escalated"] = ~c.escalated.astype(bool)
    g = _entity_rates(d, c, "not_escalated", cfg["min_scale"])
    out = []
    for row in _flagged(g, cfg["min_rate"], p["z_min"], cfg["min_cases"]).itertuples():
        ev = c[(c.entity_id == row.entity_id) & c.not_escalated]
        on_crit = int((ev.asset_criticality == "critical").sum())
        out.append(Finding(
            row.entity_id, "critical_no_escalation", "execution_gap",
            grade(row.rate, [(0.5, "critical"), (0.3, "high")], "medium"),
            f"{int(row.k)} confirmed critical incidents closed without escalation",
            (f"{int(row.k)} of {int(row.n)} closed critical cases confirmed as true positive "
             f"({fmt_pct(row.rate)}) were never escalated; {on_crit} of them were on critical assets. "
             f"Peers leave {fmt_pct(row.peer_median)} unescalated (robust z = {row.z:.1f})."),
            ev.sort_values("opened_at").case_id.tolist(), "case",
            {"rate": r(row.rate), "count": int(row.k), "critical_true_positives": int(row.n),
             "on_critical_assets": on_crit, "peer_median_rate": r(row.peer_median), "z": r(row.z, 2)},
            "critical_no_escalation"))
    return out


_NORM = re.compile(r"[^a-z0-9 ]+")


def _normalise(text: str) -> str:
    return " ".join(_NORM.sub(" ", text.lower()).split())


def _exact_pairs(x, similarity: float, chunk: int) -> tuple[np.ndarray, np.ndarray]:
    rows, cols = [], []
    for start in range(0, x.shape[0], chunk):
        s = (x[start:start + chunk] @ x.T).tocoo()
        keep = (s.data >= similarity) & (s.row + start != s.col)
        rows.append(s.row[keep] + start)
        cols.append(s.col[keep])
    return np.concatenate(rows), np.concatenate(cols)


def _candidate_pairs(x, similarity: float, chunk: int, dims: int = 64,
                     margin: float = 0.12) -> tuple[np.ndarray, np.ndarray]:
    """Fast path for many texts: find candidate pairs in a 64-d SVD projection (dense matmul),
    then keep only pairs whose exact TF-IDF cosine passes. The margin keeps the projection from
    missing true pairs; verification keeps it from adding false ones."""
    from sklearn.decomposition import TruncatedSVD
    k = max(2, min(dims, x.shape[1] - 1, x.shape[0] - 1))
    z = TruncatedSVD(k, random_state=0).fit_transform(x).astype(np.float32)
    z /= np.maximum(np.linalg.norm(z, axis=1, keepdims=True), 1e-9)
    rows, cols = [], []
    for start in range(0, z.shape[0], chunk):
        sim = z[start:start + chunk] @ z.T
        r, c = np.nonzero(sim >= similarity - margin)
        r = r + start
        keep = r < c
        r, c = r[keep], c[keep]
        if len(r):
            exact = np.asarray(x[r].multiply(x[c]).sum(axis=1)).ravel()
            ok = exact >= similarity
            rows.append(r[ok])
            cols.append(c[ok])
    if not rows:
        return np.array([], dtype=int), np.array([], dtype=int)
    return np.concatenate(rows), np.concatenate(cols)


def near_duplicate_groups(texts: pd.Series, similarity: float, chunk: int = 400,
                          exact_limit: int = 3000) -> np.ndarray:
    """Group label per text: texts whose TF-IDF cosine >= similarity share a label (transitively).

    Exact duplicates (after normalisation) are merged first, so only distinct texts are compared.
    Up to `exact_limit` distinct texts are compared exhaustively; above that, an SVD candidate
    search with exact verification is used (same groups, much faster).
    """
    norm = texts.fillna("").map(_normalise)
    uniq, inverse = np.unique(norm.to_numpy(), return_inverse=True)
    n = len(uniq)
    if n <= 1:
        return inverse
    vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1,
                          token_pattern=r"(?u)\b\w+\b")
    x = vec.fit_transform(uniq).tocsr()
    rr, cc = _exact_pairs(x, similarity, chunk) if n <= exact_limit else _candidate_pairs(x, similarity, chunk)
    from scipy.sparse import coo_matrix
    graph = coo_matrix((np.ones(len(rr)), (rr, cc)), shape=(n, n))
    _, labels = connected_components(graph, directed=False)
    return labels[inverse]


_GROUP_CACHE: dict[str, dict[str, int]] = {}


def cached_groups(texts: pd.Series, similarity: float) -> np.ndarray:
    """near_duplicate_groups, memoised per organisation on the SET of distinct normalised notes
    (order-independent) and the threshold. In the long-running API an upload changes one
    organisation's notes, so the others are not recomputed."""
    import hashlib
    norm = texts.fillna("").map(_normalise)
    uniq = sorted(set(norm))
    h = hashlib.sha1(f"{similarity}".encode())
    for t in uniq:
        h.update(t.encode("utf-8", "replace"))
        h.update(b"\x00")
    key = h.hexdigest()
    if key not in _GROUP_CACHE:
        if len(_GROUP_CACHE) > 256:
            _GROUP_CACHE.clear()
        labels = near_duplicate_groups(pd.Series(uniq), similarity)
        _GROUP_CACHE[key] = dict(zip(uniq, (int(x) for x in labels), strict=True))
    lookup = _GROUP_CACHE[key]
    return norm.map(lookup).to_numpy()


def warm_note_cache(con, similarity: float) -> int:
    """Pre-compute note groups for every organisation (used at API start-up, in the background)."""
    df = con.execute("SELECT entity_id, notes FROM cases").df()
    for _, g in df.groupby("entity_id"):
        cached_groups(g.notes, similarity)
    return df.entity_id.nunique()


def template_notes(d: Data, p: dict) -> list[Finding]:
    cfg = p["template_notes"]
    c = d.cases.copy()
    if c.empty:
        return []
    parts = []
    for _eid, grp in c.groupby("entity_id"):
        grp = grp.copy()
        grp["group"] = cached_groups(grp.notes, cfg["similarity"])
        size = grp.groupby("group").case_id.transform("size")
        grp["templated"] = (size >= cfg["min_group"]) & (grp.notes.fillna("").str.len() >= cfg["min_chars"])
        grp["group_size"] = size
        parts.append(grp)
    c = pd.concat(parts)
    g = _entity_rates(d, c, "templated", cfg["min_scale"])
    out = []
    for row in _flagged(g, cfg["min_rate"], p["z_min"], p["min_cases"]).itertuples():
        ev = c[(c.entity_id == row.entity_id) & c.templated]
        top = (ev.groupby("group").agg(n=("case_id", "size"), example=("notes", "first"))
               .sort_values("n", ascending=False).head(3))
        by_analyst = ev.assignee.value_counts().head(5).to_dict()
        analyst_share = {a: r(n / int((c.entity_id == row.entity_id).mul(c.assignee == a).sum()))
                         for a, n in by_analyst.items()}
        out.append(Finding(
            row.entity_id, "template_notes", "execution_gap",
            grade(row.rate, [(0.40, "high"), (0.15, "medium")], "low"),
            f"{int(row.k)} cases with copy-paste investigation notes",
            (f"{fmt_pct(row.rate)} of case notes ({int(row.k)} of {int(row.n)}) belong to groups of "
             f"{cfg['min_group']}+ near-identical notes (TF-IDF cosine >= {cfg['similarity']}). "
             f"Most common: \"{top.example.iloc[0][:90]}\" ({int(top.n.iloc[0])} times). "
             f"Concentrated in analysts {', '.join(list(by_analyst)[:3])}. Peer median "
             f"{fmt_pct(row.peer_median)} (robust z = {row.z:.1f})."),
            ev.sort_values("opened_at").case_id.tolist(), "case",
            {"rate": r(row.rate), "count": int(row.k), "cases": int(row.n),
             "peer_median_rate": r(row.peer_median), "z": r(row.z, 2),
             "top_templates": [{"note": t.example[:200], "count": int(t.n)} for t in top.itertuples()],
             "by_analyst": {a: int(n) for a, n in by_analyst.items()},
             "analyst_template_share": analyst_share},
            "template_notes"))
    return out


def repeated_no_remediation(d: Data, p: dict) -> list[Finding]:
    cfg = p["repeated_no_remediation"]
    a = d.alerts[d.alerts.asset_id.notna()]
    if a.empty or d.cases.empty:
        return []
    a = a[a.entity_id.isin(d.with_cases())]
    rem = d.cases.groupby("alert_id").remediation.first()
    a = a.assign(remediation=a.alert_id.map(rem))
    key = ["entity_id", "asset_id", "rule_name"]
    # Split each asset/rule history at every remediation: a stretch of min_alerts+ alerts over
    # min_span_days+ with no fix in between means the root cause was left in place that long
    # (whether or not someone eventually fixed it).
    a = a.sort_values(key + ["ts"])
    a["has_fix"] = a.remediation.notna()
    fixed = a.remediation.notna().astype(int)
    a["segment"] = fixed.groupby([a[k] for k in key]).cumsum() - fixed  # fix closes its segment
    seg = key + ["segment"]
    g = a.groupby(seg).agg(n=("alert_id", "size"), first=("ts", "min"), last=("ts", "max"),
                           ended_by_fix=("has_fix", "max")).reset_index()
    g["span_days"] = (g["last"] - g["first"]).dt.total_seconds() / 86400
    hits = g[(g.n >= cfg["min_alerts"]) & (g.span_days >= cfg["min_span_days"])]
    crit = dict(zip(d.assets.asset_id, d.assets.criticality, strict=True))
    case_of = d.cases.set_index("alert_id").case_id
    out = []
    for eid, h in hits.groupby("entity_id"):
        ae = a[a.entity_id == eid]
        al = ae[pd.MultiIndex.from_frame(ae[["asset_id", "rule_name", "segment"]]).isin(
            list(h[["asset_id", "rule_name", "segment"]].itertuples(index=False, name=None)))]
        case_ids = al.alert_id.map(case_of).dropna().tolist()
        h = h.groupby(["asset_id", "rule_name"]).agg(
            n=("n", "sum"), span_days=("span_days", "max"),
            ended_by_fix=("ended_by_fix", "any")).reset_index()
        n_crit = sum(crit.get(x) == "critical" for x in h.asset_id)
        worst = h.sort_values("n", ascending=False).iloc[0]
        out.append(Finding(
            eid, "repeated_no_remediation", "execution_gap",
            "high" if n_crit or len(h) >= 3 else "medium",
            f"{len(h)} asset/rule pairs keep alerting with no remediation",
            (f"{len(h)} asset/rule combinations fired {cfg['min_alerts']}+ times over "
             f"{cfg['min_span_days']}+ days without any remediation in between ({int(h.n.sum())} alerts). "
             f"Worst: '{worst.rule_name}' on {worst.asset_id}, {int(worst.n)} alerts over "
             f"{worst.span_days:.0f} days. {n_crit} of the assets are critical; "
             f"{int(h.ended_by_fix.sum())} were eventually remediated."),
            case_ids, "case",
            {"pairs": [{"asset_id": x.asset_id, "rule_name": x.rule_name, "alerts": int(x.n),
                        "span_days": r(x.span_days, 1), "criticality": crit.get(x.asset_id),
                        "eventually_remediated": bool(x.ended_by_fix)}
                       for x in h.sort_values("n", ascending=False).itertuples()],
             "alerts": int(h.n.sum()), "critical_assets": int(n_crit)},
            "repeated_no_remediation"))
    return out


def sla_gaming(d: Data, p: dict) -> list[Finding]:
    """Closures bunched just before the SLA deadline (a sign of closing to the metric)."""
    cfg = p["sla_gaming"]
    c = _closed(d)
    c = c[c.sla_deadline.notna()].copy()
    if c.empty:
        return []
    window = (c.sla_deadline - c.opened_at).dt.total_seconds()
    slack = (c.sla_deadline - c.closed_at).dt.total_seconds() / window  # 0 = at deadline
    c["final"] = (slack >= 0) & (slack < cfg["final_window"])
    c["prev"] = (slack >= cfg["final_window"]) & (slack < cfg["final_window"] + cfg["prev_window"])
    g = _entity_rates(d, c, "final", cfg["min_scale"])
    prev = c.groupby("entity_id").prev.sum()
    g["prev_k"] = g.entity_id.map(prev)
    # ratio of closure density in the final window vs the window just before it
    g["ratio"] = (g.k / cfg["final_window"]) / ((g.prev_k + 1) / cfg["prev_window"])
    out = []
    for row in _flagged(g, cfg["min_share"], p["z_min"], p["min_cases"]).itertuples():
        if row.ratio < cfg["min_ratio"]:
            continue
        ev = c[(c.entity_id == row.entity_id) & c.final]
        out.append(Finding(
            row.entity_id, "sla_gaming", "execution_gap",
            grade(row.rate, [(0.30, "high"), (0.12, "medium")], "low"),
            f"{int(row.k)} cases closed in the last {int(cfg['final_window'] * 100)}% of the SLA window",
            (f"{fmt_pct(row.rate)} of closed cases ({int(row.k)}) were closed in the final "
             f"{int(cfg['final_window'] * 100)}% of their SLA window, {row.ratio:.1f}x denser than the "
             f"window just before it. Genuine work tails off near a deadline; bunching just inside it "
             f"suggests cases are closed to meet the metric. Peer median {fmt_pct(row.peer_median)} "
             f"(robust z = {row.z:.1f})."),
            ev.sort_values("opened_at").case_id.tolist(), "case",
            {"rate": r(row.rate), "count": int(row.k), "closed_cases": int(row.n),
             "bunching_ratio": r(row.ratio, 2), "peer_median_rate": r(row.peer_median), "z": r(row.z, 2),
             "by_severity": {k: int(v) for k, v in ev.severity.value_counts().items()}},
            "sla_gaming"))
    return out


def sla_breach(d: Data, p: dict) -> list[Finding]:
    """Slow-tail time-to-close outliers: share of cases closed after the SLA deadline."""
    cfg = p["sla_breach"]
    c = _closed(d)
    c = c[c.sla_deadline.notna()].copy()
    if c.empty:
        return []
    c["breach"] = c.closed_at > c.sla_deadline
    g = _entity_rates(d, c, "breach", cfg["min_scale"])
    out = []
    for row in _flagged(g, cfg["min_rate"], p["z_min"], p["min_cases"]).itertuples():
        ev = c[(c.entity_id == row.entity_id) & c.breach]
        out.append(Finding(
            row.entity_id, "sla_breach", "execution_gap",
            grade(row.rate, [(0.4, "high")], "medium"),
            f"{int(row.k)} cases closed after their SLA deadline",
            (f"{fmt_pct(row.rate)} of closed cases breached their SLA, against a peer median of "
             f"{fmt_pct(row.peer_median)} (robust z = {row.z:.1f})."),
            ev.case_id.tolist(), "case",
            {"rate": r(row.rate), "count": int(row.k), "peer_median_rate": r(row.peer_median),
             "z": r(row.z, 2)}, "sla_breach"))
    return out


DETECTORS = [fast_closure, critical_no_escalation, template_notes, repeated_no_remediation,
             sla_gaming, sla_breach]
