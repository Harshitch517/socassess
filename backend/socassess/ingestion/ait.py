"""Map the AIT Alert Data Set sample into the unified schema.

Each AIT scenario becomes one entity (source='ait'); hosts become assets. AIT has no
case-management data, so only alert-based analytics (clustering, category coverage, volume)
apply to these entities. Severity comes from the Wazuh rule level (0-3 low, 4-7 medium,
8-11 high, 12+ critical); AMiner anomalies are 'medium'. Asset criticality is unknown in AIT
and is set to 'medium'.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

CATEGORY_RULES = [  # (substring in rule groups / description, category); first match wins
    ("authentication_failed", "brute_force"), ("invalid_login", "brute_force"),
    ("web_scan", "recon"), ("recon", "recon"), ("attack", "web_attack"),
    ("virus", "malware"), ("authentication_success", "authentication"),
    ("dns", "dns_anomaly"), ("audit", "host_anomaly"), ("ids", "network_ids"),
    ("apache", "web_anomaly"), ("monitoring", "resource_anomaly"),
]


def _category(groups: str | None) -> str:
    g = (groups or "").lower()
    for key, cat in CATEGORY_RULES:
        if key in g:
            return cat
    return "other"


def load_ait_tables(sample: str | Path) -> dict[str, pd.DataFrame]:
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    df = con.execute(f"""
        SELECT scenario, detector, ts, coalesce(host, 'unknown') AS host, rule_id, rule_level,
               description, rule_groups,
               row_number() OVER (PARTITION BY scenario ORDER BY ts, detector, rule_id) AS n
        FROM read_parquet('{Path(sample).as_posix()}')""").df()
    df["entity_id"] = "AIT-" + df["scenario"]
    df["asset_id"] = df["entity_id"] + ":" + df["host"]
    lvl = df["rule_level"]
    df["severity"] = pd.cut(lvl.fillna(5), [-1, 3, 7, 11, 99],
                            labels=["low", "medium", "high", "critical"]).astype(str)
    df["category"] = (df["rule_groups"].fillna("") + " " + df["description"].fillna("")).map(_category)
    alerts = pd.DataFrame({
        "alert_id": df["entity_id"] + "-" + df["n"].astype(str).str.zfill(7),
        "entity_id": df["entity_id"], "asset_id": df["asset_id"], "ts": df["ts"],
        "category": df["category"], "severity": df["severity"],
        "rule_name": df["description"], "source": df["detector"], "case_id": None})
    ent = df.groupby("entity_id").agg(period_start=("ts", "min"), period_end=("ts", "max")).reset_index()
    ent["name"] = "AIT testbed " + ent["entity_id"].str[4:]
    ent["sector"], ent["size"], ent["region"], ent["source"] = "enterprise_testbed", "medium", None, "ait"
    assets = df.drop_duplicates("asset_id")[["asset_id", "entity_id", "host"]].rename(
        columns={"host": "hostname"})
    assets["criticality"], assets["asset_type"], assets["owner_team"] = "medium", None, None
    return {"entities": ent, "assets": assets, "alerts": alerts}
