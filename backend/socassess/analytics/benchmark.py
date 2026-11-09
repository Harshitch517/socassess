"""Per-entity operational metrics, peer benchmarking, anomaly scoring and weekly trends."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

from socassess.analytics.common import Data, Finding, r

# metric -> (description, direction where "worse" lies: +1 high is bad, -1 low is bad, 0 either)
METRICS = {
    "alerts_per_asset_day": ("Alerts per asset per day", -1),
    "high_crit_share": ("Share of alerts that are high/critical", 0),
    "median_ttc_sla_ratio": ("Median time-to-close as a fraction of SLA", 0),
    "fast_close_share": ("High/critical cases closed in < 10 min", 1),
    "sla_breach_rate": ("Cases closed after the SLA deadline", 1),
    "deadline_bunching_share": ("Cases closed in the last 5% of the SLA window", 1),
    "escalation_rate_crit_tp": ("Critical true positives escalated", -1),
    "false_positive_rate": ("Cases closed as false positive", 0),
    "open_case_share": ("Cases still open at period end", 1),
    "uncased_alert_share": ("High/critical alerts without a case", 1),
    "unique_note_share": ("Distinct investigation notes / cases", -1),
    "median_note_words": ("Median words per note", -1),
    "remediation_rate_tp": ("True positives with a remediation recorded", -1),
    "category_coverage": ("Alert categories seen / categories seen by peers", -1),
    "silent_critical_asset_share": ("Critical assets with mostly zero telemetry", 1),
    "cases_per_analyst_day": ("Cases per analyst per day", 0),
}


def entity_metrics(d: Data) -> pd.DataFrame:
    ent = d.entities.set_index("entity_id")
    rows = {}
    all_cats = d.alerts.groupby("entity_id").category.agg(set)
    for eid in ent.index:
        al = d.alerts[d.alerts.entity_id == eid]
        cs = d.cases[d.cases.entity_id == eid]
        assets = d.assets[d.assets.entity_id == eid]
        m: dict[str, float] = {}
        days = max(1, (al.ts.max() - al.ts.min()).days + 1) if len(al) else np.nan
        m["alerts_per_asset_day"] = len(al) / max(1, len(assets)) / days if len(al) else np.nan
        m["high_crit_share"] = al.severity.isin(["high", "critical"]).mean() if len(al) else np.nan
        peers_src = [e for e in ent.index if ent.at[e, "source"] == ent.at[eid, "source"] and e in all_cats]
        peer_cats = set().union(*(all_cats[e] for e in peers_src)) if peers_src else set()
        m["category_coverage"] = len(all_cats.get(eid, set())) / len(peer_cats) if peer_cats else np.nan
        if len(cs):
            closed = cs[cs.status == "closed"]
            sla_len = (cs.sla_deadline - cs.opened_at).dt.total_seconds() / 60
            m["median_ttc_sla_ratio"] = float((closed.ttc_min / sla_len[closed.index]).median())
            hc = closed[closed.severity.isin(["high", "critical"])]
            m["fast_close_share"] = float((hc.ttc_min < 10).mean()) if len(hc) else np.nan
            m["sla_breach_rate"] = float((closed.closed_at > closed.sla_deadline).mean())
            slack = (closed.sla_deadline - closed.closed_at).dt.total_seconds() / 60 / sla_len[closed.index]
            m["deadline_bunching_share"] = float(((slack >= 0) & (slack < 0.05)).mean())
            ctp = closed[(closed.severity == "critical") & (closed.disposition == "true_positive")]
            m["escalation_rate_crit_tp"] = float(ctp.escalated.astype(bool).mean()) if len(ctp) else np.nan
            m["false_positive_rate"] = float((closed.disposition == "false_positive").mean())
            m["open_case_share"] = float((cs.status == "open").mean())
            hca = al[al.severity.isin(["high", "critical"])]
            m["uncased_alert_share"] = float((hca.case_id.isna() & ~hca.alert_id.isin(cs.alert_id)).mean())
            notes = cs.notes.fillna("").str.lower().str.strip()
            m["unique_note_share"] = notes.nunique() / len(notes)
            m["median_note_words"] = float(notes.str.split().str.len().median())
            tp = cs[cs.disposition == "true_positive"]
            m["remediation_rate_tp"] = float(tp.remediation.notna().mean()) if len(tp) else np.nan
            m["cases_per_analyst_day"] = len(cs) / max(1, cs.assignee.nunique()) / days
        if not d.telemetry.empty and (d.telemetry.entity_id == eid).any():
            t = d.telemetry[d.telemetry.entity_id == eid]
            zero = t.groupby("asset_id").event_count.apply(lambda s: (s == 0).mean())
            crit = assets[assets.criticality == "critical"].asset_id
            m["silent_critical_asset_share"] = float((zero.reindex(crit).fillna(1) >= 0.5).mean()) \
                if len(crit) else np.nan
        rows[eid] = m
    df = pd.DataFrame.from_dict(rows, orient="index").reindex(columns=list(METRICS))
    df.index.name = "entity_id"
    return df


def benchmark(d: Data, metrics: pd.DataFrame) -> pd.DataFrame:
    """Long table: entity, metric, value, peer group (same source + size), peer median, percentile, z."""
    ent = d.entities.set_index("entity_id")
    out = []
    for eid in metrics.index:
        src, size = ent.at[eid, "source"], ent.at[eid, "size"]
        same_src = [e for e in metrics.index if ent.at[e, "source"] == src]
        size_peers = [e for e in same_src if ent.at[e, "size"] == size and e != eid]
        for m, (desc, direction) in METRICS.items():
            v = metrics.at[eid, m]
            if pd.isna(v):
                continue
            col = metrics.loc[[e for e in same_src if e != eid], m].dropna()  # peers only, never self
            if col.empty:
                continue
            peers = metrics.loc[size_peers, m].dropna() if size_peers else pd.Series(dtype=float)
            med = float(col.median())
            mad = float((col - med).abs().median()) * 1.4826
            # floor the scale at 5% of the median so near-identical peers don't turn tiny gaps into huge z
            scale = max(mad, 0.05 * abs(med), 1e-9)
            z = (v - med) / scale if (mad > 0 or v != med) else 0.0
            out.append({"entity_id": eid, "metric": m, "description": desc, "direction": direction,
                        "value": r(v), "peer_median_all": r(med),
                        "peer_median_size": r(float(peers.median())) if len(peers) else None,
                        "size_peers": size_peers, "percentile": r(float((col < v).mean() + 0.5 * (col == v).mean())),
                        "z": r(float(np.clip(z, -50, 50)), 2), "n_peers": len(col)})
    return pd.DataFrame(out)


def anomalies(d: Data, metrics: pd.DataFrame, bench: pd.DataFrame, p: dict) -> tuple[pd.Series, list[Finding]]:
    """IsolationForest score per entity (within source) + findings for entities it isolates."""
    cfg = p["anomaly"]
    ent = d.entities.set_index("entity_id")
    scores = pd.Series(np.nan, index=metrics.index, name="anomaly_score")
    findings = []
    for _src, ids in metrics.groupby(ent.source.reindex(metrics.index)).groups.items():
        x = metrics.loc[ids].dropna(axis=1, how="any")
        if len(x) < cfg["min_entities"] or x.shape[1] < 2:
            continue
        xs = RobustScaler().fit_transform(x)
        xs = np.nan_to_num(np.clip(xs, -20, 20))
        forest = IsolationForest(n_estimators=cfg["n_estimators"], random_state=cfg["random_state"],
                                 contamination="auto").fit(xs)
        s = -forest.score_samples(xs)  # higher = more anomalous, ~0.5 typical
        scores.loc[x.index] = s
        pred = forest.predict(xs)
        for eid, sc, pr in zip(x.index, s, pred, strict=True):
            b = bench[(bench.entity_id == eid) & bench.metric.isin(x.columns)].copy()
            drivers = b[b.z.abs() >= cfg["z_flag"]].sort_values("z", key=abs, ascending=False)
            if pr != -1 or drivers.empty:
                continue
            txt = "; ".join(f"{x.description} = {x.value} (peer median {x.peer_median_all}, z {x.z:+.1f})"
                            for x in drivers.head(4).itertuples())
            findings.append(Finding(
                eid, "operational_anomaly", "anomaly", "medium" if sc < 0.6 else "high",
                "Operational profile is unusual for its peers",
                (f"IsolationForest isolates this entity's operating metrics from its {len(x) - 1} peers "
                 f"(score {sc:.2f}; ~0.5 is typical). Main drivers: {txt}."),
                [], "none",
                {"anomaly_score": r(sc, 3), "drivers": [
                    {"metric": x.metric, "value": x.value, "peer_median": x.peer_median_all, "z": x.z}
                    for x in drivers.head(6).itertuples()]},
                "isolation_forest"))
    return scores, findings


def weekly_trends(d: Data) -> pd.DataFrame:
    a = d.alerts.assign(week=d.alerts.ts.dt.tz_convert(None).dt.to_period("W").dt.start_time)
    t = a.groupby(["entity_id", "week"]).agg(
        alerts=("alert_id", "size"),
        high_critical=("severity", lambda s: int(s.isin(["high", "critical"]).sum()))).reset_index()
    if not d.cases.empty:
        c = d.cases[d.cases.closed_at.notna()].copy()
        c["week"] = c.closed_at.dt.tz_convert(None).dt.to_period("W").dt.start_time
        c["fast"] = c.severity.isin(["high", "critical"]) & (c.ttc_min < 10)
        c["breach"] = c.closed_at > c.sla_deadline
        cw = c.groupby(["entity_id", "week"]).agg(
            cases_closed=("case_id", "size"), median_ttc_hours=("ttc_min", lambda s: s.median() / 60),
            fast_closures=("fast", "sum"), sla_breaches=("breach", "sum"),
            escalated=("escalated", lambda s: int(s.astype(bool).sum()))).reset_index()
        t = t.merge(cw, on=["entity_id", "week"], how="left")
    t["week"] = t.week.dt.strftime("%Y-%m-%d")
    return t

