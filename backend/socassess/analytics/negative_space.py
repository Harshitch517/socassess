"""Negative-space detectors: what should be in the data but is not."""

from __future__ import annotations

import numpy as np
import pandas as pd

from socassess.analytics.common import Data, Finding, fmt_pct, peer_median, peer_z, r


def silent_critical_assets(d: Data, p: dict) -> list[Finding]:
    """Critical assets with no or almost no telemetry (blind spots)."""
    cfg = p["silent_assets"]
    if d.telemetry.empty:
        return []
    tel = d.telemetry.copy()
    tel["date"] = pd.to_datetime(tel["date"])
    with_tel = set(tel.entity_id)
    crit = d.assets[(d.assets.criticality == "critical") & d.assets.entity_id.isin(with_tel)]
    if crit.empty:
        return []
    last = tel.groupby("entity_id").date.transform("max")
    tel["recent"] = tel.date > last - pd.Timedelta(days=cfg["recent_days"])
    per_asset = tel.groupby("asset_id").agg(
        days=("event_count", "size"), zero_share=("event_count", lambda s: float((s == 0).mean())),
        median_events=("event_count", "median"))
    recent = tel[tel.recent].groupby("asset_id").event_count.median().rename("recent_median")
    per_asset = per_asset.join(recent)
    types = d.assets.set_index("asset_id").asset_type
    per_asset["asset_type"] = per_asset.index.map(types)
    type_median = per_asset.groupby("asset_type").median_events.median()
    per_asset["type_median"] = per_asset.asset_type.map(type_median)
    alert_counts = d.alerts.groupby("asset_id").size()
    rows = []
    for a in crit.itertuples():
        if a.asset_id not in per_asset.index:
            rows.append((a.entity_id, a.asset_id, a.asset_type, "no telemetry rows", 1.0, 0.0, 0))
            continue
        s = per_asset.loc[a.asset_id]
        base = s.type_median if s.type_median and np.isfinite(s.type_median) else np.nan
        low = (base > 0) and s.recent_median < cfg["low_fraction"] * base
        if s.zero_share >= cfg["zero_day_share"] or low:
            why = (f"{fmt_pct(s.zero_share)} of days with zero events" if s.zero_share >= cfg["zero_day_share"]
                   else f"recent median {s.recent_median:.0f} events/day vs {base:.0f} typical for "
                        f"{a.asset_type}")
            rows.append((a.entity_id, a.asset_id, a.asset_type, why, float(s.zero_share),
                         float(s.recent_median), int(alert_counts.get(a.asset_id, 0))))
    out = []
    df = pd.DataFrame(rows, columns=["entity_id", "asset_id", "asset_type", "why", "zero_share",
                                     "recent_median", "alerts"])
    n_crit = crit.groupby("entity_id").size()
    for eid, g in df.groupby("entity_id"):
        share = len(g) / n_crit[eid]
        sev = "critical" if share >= 0.2 or len(g) >= 5 else "high"
        types_txt = ", ".join(f"{k} x{v}" for k, v in g.asset_type.value_counts().items())
        out.append(Finding(
            eid, "silent_critical_assets", "negative_space", sev,
            f"{len(g)} critical assets are silent",
            (f"{len(g)} of {int(n_crit[eid])} critical assets ({fmt_pct(share)}) send no or almost no "
             f"telemetry ({types_txt}); together they raised {int(g.alerts.sum())} alerts in the period. "
             f"An attack on these hosts would not be seen. Example: {g.asset_id.iloc[0]}: {g.why.iloc[0]}."),
            g.asset_id.tolist(), "asset",
            {"silent_assets": len(g), "critical_assets": int(n_crit[eid]), "share": r(share),
             "assets": [{"asset_id": x.asset_id, "asset_type": x.asset_type, "reason": x.why,
                         "zero_day_share": r(x.zero_share), "recent_median_events": r(x.recent_median, 1),
                         "alerts": x.alerts} for x in g.itertuples()]},
            "silent_critical_assets"))
    return out


def missing_categories(d: Data, p: dict) -> list[Finding]:
    """Alert categories that peers see but this entity never reports."""
    cfg = p["missing_categories"]
    ent = d.entities.set_index("entity_id")
    counts = d.alerts.groupby(["entity_id", "category"]).size().unstack(fill_value=0)
    if counts.empty:
        return []
    fam_map = cfg["sector_family"]
    family = ent.sector.map(lambda s: fam_map.get(s, "general"))
    out = []
    for eid in counts.index:
        src = ent.at[eid, "peer_group"]
        same_src = [e for e in counts.index if e != eid and ent.at[e, "peer_group"] == src]
        fam_peers = [e for e in same_src if family[e] == family[eid]]
        expected: dict[str, tuple[float, str]] = {}
        for peers, label in ((same_src, "all peers"), (fam_peers, f"{family[eid]} sector peers")):
            if len(peers) < 3:
                continue
            presence = (counts.loc[peers] >= cfg["min_alerts_present"]).mean()
            for cat, share in presence[presence >= cfg["peer_presence"]].items():
                expected.setdefault(cat, (float(share), label))
        # Only judge coverage when the entity uses the peers' category vocabulary: an export with its own
        # naming (or no categories at all) would otherwise look like it is "missing" everything.
        peer_vocab = set(counts.columns[(counts.loc[same_src] > 0).any()]) if same_src else set()
        own = counts.loc[eid]
        shared_share = own[[c for c in own.index if c in peer_vocab]].sum() / max(1, own.sum())
        if shared_share < cfg.get("min_shared_vocabulary", 0.5):
            continue
        missing = [c for c in expected if counts.at[eid, c] == 0] if expected else []
        if not missing:
            continue
        high = [c for c in missing if c in cfg["high_impact"]]
        detail = "; ".join(f"{c} (seen by {fmt_pct(expected[c][0])} of {expected[c][1]})" for c in missing)
        out.append(Finding(
            eid, "missing_categories", "negative_space", "high" if high else "medium",
            f"No {', '.join(missing)} alerts at all",
            (f"The entity reported zero alerts in {len(missing)} categor{'y' if len(missing) == 1 else 'ies'} "
             f"that peers routinely see: {detail}. Either the detection content or the log sources for these "
             f"techniques are missing, or alerts are being suppressed."),
            [], "none",
            {"missing": missing, "high_impact_missing": high,
             "peer_presence": {c: r(expected[c][0]) for c in missing},
             "entity_categories": {k: int(v) for k, v in counts.loc[eid][counts.loc[eid] > 0].items()}},
            "missing_categories"))
    return out


def missing_records(d: Data, p: dict) -> list[Finding]:
    """High/critical alerts with no case, and escalations flagged but never recorded."""
    cfg = p["missing_records"]
    has_cases = d.with_cases()
    if not has_cases:
        return []
    a = d.alerts[d.alerts.entity_id.isin(has_cases) & d.alerts.severity.isin(["high", "critical"])]
    cased = set(d.cases.alert_id.dropna())
    uncased = a[a.case_id.isna() & ~a.alert_id.isin(cased)]
    esc_cases = set(d.escalations.case_id)
    flagged = d.cases[d.cases.escalated.astype(bool)]
    unrecorded = flagged[~flagged.case_id.isin(esc_cases)]
    n_hc = a.groupby("entity_id").size()
    n_flag = flagged.groupby("entity_id").size()
    out = []
    for eid in sorted(has_cases):
        u = uncased[uncased.entity_id == eid]
        e = unrecorded[unrecorded.entity_id == eid]
        u_rate = len(u) / n_hc.get(eid, np.nan) if n_hc.get(eid) else 0.0
        e_rate = len(e) / n_flag.get(eid, np.nan) if n_flag.get(eid) else 0.0
        u_hit = len(u) >= cfg["min_items"] and u_rate >= cfg["min_uncased_rate"]
        e_hit = len(e) >= cfg["min_items"] and e_rate >= cfg["min_unrecorded_rate"]
        if not (u_hit or e_hit):
            continue
        parts = []
        if u_hit:
            parts.append(f"{len(u)} high/critical alerts ({fmt_pct(u_rate)}) have no case record")
        if e_hit:
            parts.append(f"{len(e)} cases marked escalated ({fmt_pct(e_rate)}) have no escalation record")
        out.append(Finding(
            eid, "missing_records", "negative_space",
            "critical" if u_rate >= 0.1 or e_rate >= 0.3 else "high",
            "Missing case or escalation records",
            "; ".join(parts) + ". Work that leaves no record cannot be audited and may not have happened.",
            (u.alert_id.tolist() if u_hit else []) + (e.case_id.tolist() if e_hit else []),
            "alert+case",
            {"uncased_high_critical_alerts": len(u), "uncased_rate": r(u_rate),
             "escalated_without_record": len(e), "unrecorded_rate": r(e_rate),
             "alert_ids": u.alert_id.tolist()[:50] if u_hit else [],
             "case_ids": e.case_id.tolist()[:50] if e_hit else []},
            "missing_records"))
    return out


def low_activity(d: Data, p: dict) -> list[Finding]:
    """Alert volume per asset far below same-source peers."""
    cfg = p["low_activity"]
    ent = d.entities.set_index("entity_id")
    n_assets = d.assets.groupby("entity_id").size()
    days = d.alerts.groupby("entity_id").ts.agg(lambda s: max(1.0, (s.max() - s.min()).days + 1))
    vol = d.alerts.groupby("entity_id").size()
    df = pd.DataFrame({"alerts": vol, "assets": n_assets, "days": days}).dropna()
    if len(df) < 3:
        return []
    df["rate"] = df.alerts / df.assets / df.days
    df["source"] = ent.peer_group.reindex(df.index)
    df["log_rate"] = np.log(df.rate)
    df["z"] = peer_z(df.log_rate, df.source, cfg["min_scale"])
    df["peer_median"] = np.exp(peer_median(df.log_rate, df.source))
    df["ratio"] = df.rate / df.peer_median
    tel = (d.telemetry.groupby("entity_id").event_count.sum() / df.assets / df.days
           if not d.telemetry.empty else pd.Series(dtype=float))
    tel_peer = tel.median() if len(tel) else np.nan
    out = []
    for eid, row in df[(df.ratio <= cfg["max_ratio"]) & (df.z <= cfg["z_max"])].iterrows():
        t = tel.get(eid, np.nan)
        tel_txt = (f" Telemetry volume is {t:.0f} events/asset/day vs a peer median of {tel_peer:.0f}, so "
                   "logs are arriving; the gap is in detection or alert handling."
                   if np.isfinite(t) and t >= 0.5 * tel_peer else "")
        out.append(Finding(
            eid, "low_activity", "negative_space", "high" if row.ratio <= 0.2 else "medium",
            f"Alert volume is {row.ratio:.0%} of peers",
            (f"{int(row.alerts)} alerts over {int(row.days)} days for {int(row.assets)} assets "
             f"= {row.rate:.3f} alerts/asset/day, against a peer median of {row.peer_median:.3f} "
             f"(robust z on log scale = {row.z:.1f}).{tel_txt}"),
            [], "none",
            {"alerts": int(row.alerts), "assets": int(row.assets), "rate": r(row.rate),
             "peer_median_rate": r(row.peer_median), "ratio": r(row.ratio), "z": r(row.z, 2),
             "telemetry_per_asset_day": r(t, 1), "peer_telemetry_per_asset_day": r(tel_peer, 1)},
            "low_activity"))
    return out


DETECTORS = [silent_critical_assets, missing_categories, missing_records, low_activity]
