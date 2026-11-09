"""Alert pattern clustering, per entity and across entities.

Unit of clustering = one *alert pattern*: all alerts of one rule at one entity. Each pattern is
described by behaviour (volume, spread over assets and days, burstiness, after-hours share,
severity) and by its rule text (TF-IDF -> truncated SVD). HDBSCAN groups patterns that look
alike; a cluster that spans several entities is a recurring cross-entity pattern. Clusters are
summarised in plain words so a supervisor can read them without the feature vectors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler

from socassess.analytics.common import SEV_RANK, Data, r

BEHAVIOUR = ["log_alerts", "asset_spread", "active_day_share", "burstiness", "after_hours_share",
             "severity_mean"]


def pattern_table(d: Data) -> pd.DataFrame:
    a = d.alerts.copy()
    a["rule_name"] = a.rule_name.fillna(a.category)
    a["day"] = a.ts.dt.floor("D")
    a["hour"] = a.ts.dt.hour
    a["sev"] = a.severity.map(SEV_RANK)
    span = a.groupby("entity_id").day.agg(lambda s: max(1, (s.max() - s.min()).days + 1))
    n_assets = d.assets.groupby("entity_id").size()
    daily = a.groupby(["entity_id", "rule_name", "day"]).size()
    burst = daily.groupby(level=[0, 1]).agg(lambda s: s.max() / s.mean())
    g = a.groupby(["entity_id", "rule_name"]).agg(
        category=("category", lambda s: s.mode().iat[0]), alerts=("alert_id", "size"),
        assets=("asset_id", "nunique"), active_days=("day", "nunique"),
        after_hours_share=("hour", lambda h: float(((h < 7) | (h >= 20)).mean())),
        severity_mean=("sev", "mean"), first_seen=("ts", "min"), last_seen=("ts", "max"))
    g["burstiness"] = burst
    g = g.reset_index()
    g["log_alerts"] = np.log10(g.alerts)
    g["asset_spread"] = g.assets / g.entity_id.map(n_assets).clip(lower=1)
    g["active_day_share"] = g.active_days / g.entity_id.map(span)
    return g


def cluster_patterns(d: Data, p: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (patterns with cluster_id, cluster summaries)."""
    cfg = p["clustering"]
    g = pattern_table(d)
    if len(g) < cfg["min_cluster_size"] * 2:
        g["cluster_id"] = -1
        return g, pd.DataFrame()
    text = (g.rule_name + " " + g.category.str.replace("_", " ")).str.lower()
    tf = TfidfVectorizer(min_df=1, sublinear_tf=True).fit_transform(text)
    dims = max(1, min(cfg["svd_dims"], tf.shape[1] - 1, len(g) - 1))
    sem = TruncatedSVD(dims, random_state=cfg["random_state"]).fit_transform(tf)
    beh = StandardScaler().fit_transform(g[BEHAVIOUR].fillna(0))
    x = np.hstack([beh, sem * np.sqrt(len(BEHAVIOUR) / dims) * 2])  # text and behaviour weighted alike
    labels = HDBSCAN(min_cluster_size=cfg["min_cluster_size"], copy=True).fit_predict(x)
    g["cluster_id"] = labels
    summaries = []
    overall = g[BEHAVIOUR].median()
    for cid, c in g[g.cluster_id >= 0].groupby("cluster_id"):
        top_rules = c.groupby("rule_name").alerts.sum().sort_values(ascending=False).head(5)
        traits = []
        med = c[BEHAVIOUR].median()
        if med.log_alerts > overall.log_alerts + 0.5:
            traits.append("high volume")
        elif med.log_alerts < overall.log_alerts - 0.5:
            traits.append("low volume")
        if med.asset_spread > max(0.2, overall.asset_spread * 2):
            traits.append("spread over many assets")
        elif med.asset_spread < overall.asset_spread / 2:
            traits.append("concentrated on few assets")
        if med.burstiness > overall.burstiness * 1.5:
            traits.append("bursty")
        if med.after_hours_share > overall.after_hours_share + 0.15:
            traits.append("after-hours")
        if med.severity_mean >= 3:
            traits.append("mostly high/critical severity")
        cats = c.category.value_counts()
        ents = sorted(c.entity_id.unique())
        summaries.append({
            "cluster_id": int(cid), "patterns": len(c), "alerts": int(c.alerts.sum()),
            "entities": ents, "n_entities": len(ents), "cross_entity": len(ents) > 1,
            "main_category": cats.index[0], "categories": {k: int(v) for k, v in cats.items()},
            "top_rules": {k: int(v) for k, v in top_rules.items()},
            "label": f"{cats.index[0].replace('_', ' ')}: " + (", ".join(traits) or "typical profile"),
            "profile": {k: r(v, 3) for k, v in med.items()},
        })
    s = pd.DataFrame(summaries).sort_values("alerts", ascending=False) if summaries else pd.DataFrame()
    return g, s
