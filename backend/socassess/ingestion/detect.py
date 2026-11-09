"""Offline auto-classification of an upload: what kind of data it is, which sector, which size.

Used when the user does not classify their input. Every guess is a plain rule on the column
names and values, and comes with the reasons it was made, so the user can check and correct it.
Nothing leaves the machine.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

import pandas as pd

from socassess.ingestion.adapt import ALERT_ALIASES, _key

DATA_TYPES = {
    "alerts": "Security alerts (SIEM / EDR / IDS)",
    "cases": "Incident / case records",
    "assets": "Asset inventory",
    "full": "Full SOC export (several tables)",
    "telemetry": "Log volume (telemetry)",
}
SECTORS = ["power", "banking", "telecom", "transport", "health", "government", "water", "other"]
SIZES = ["small", "medium", "large"]

# keyword -> sector; matched as whole words / name fragments in file name, organisation, hosts and rule text
SECTOR_KEYWORDS: dict[str, list[str]] = {
    "power": ["power", "grid", "substation", "scada", "plc", "hmi", "rtu", "energy", "electric", "generation",
              "transmission", "nldc", "sldc", "discom", "thermal", "hydro", "solar"],
    "banking": ["bank", "banking", "payment", "payments", "atm", "swift", "upi", "cbs", "corebanking", "card",
                "fintech", "treasury", "nbfc", "insurance"],
    "telecom": ["telecom", "telco", "5g", "4g", "lte", "bts", "ss7", "msc", "isp", "mobile", "network operator"],
    "transport": ["rail", "railway", "metro", "airport", "aviation", "port", "shipping", "signal", "signalling",
                  "atc", "logistics", "highway"],
    "health": ["hospital", "health", "patient", "ehr", "emr", "his", "pacs", "clinic", "medical", "pharma"],
    "government": ["gov", "govt", "government", "ministry", "egov", "nic", "municipal", "police", "court",
                   "department"],
    "water": ["water", "pump", "sewage", "reservoir", "jal", "treatment plant", "desalination"],
}
CASE_COLS = {"closedat", "resolvedat", "closed", "assignee", "analyst", "owner", "disposition", "status", "resolution",
             "sladeadline", "sladue", "escalated", "verdict", "incidentgrade", "notes", "comment"}
ASSET_COLS = {"criticality", "assettype", "devicetype", "assetowner", "ownerteam", "businessunit", "os",
              "operatingsystem", "macaddress"}
TELEMETRY_COLS = {"eventcount", "eventsperday", "logvolume", "events", "count", "volume"}


@dataclass
class Guess:
    value: str
    label: str
    confidence: str  # high | medium | low
    reasons: list[str] = field(default_factory=list)


@dataclass
class Detection:
    data_type: Guess
    sector: Guess
    size: Guess
    rows: int
    tables: dict[str, int]
    columns: list[str]
    mapping: dict[str, str]
    missing_for_full: list[str]
    preview: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


def _data_type(raw: dict, extra: dict, keys: set[str]) -> Guess:
    known = [t for t in raw if t in {"alerts", "cases", "assets", "escalations", "telemetry"}]
    if len(known) >= 2:
        return Guess("full", DATA_TYPES["full"], "high",
                     [f"the upload contains {len(known)} recognised tables: {', '.join(sorted(known))}"])
    if known:
        t = known[0] if known[0] in DATA_TYPES else "alerts"
        return Guess(t, DATA_TYPES[t], "high", [f"a table named '{known[0]}' was found"])
    hits = {
        "cases": sorted(keys & CASE_COLS),
        "assets": sorted(keys & ASSET_COLS),
        "telemetry": sorted(keys & TELEMETRY_COLS),
    }
    alert_hits = sorted(k for k in keys if any(k in names for t, names in ALERT_ALIASES.items()
                                                if t in ("ts", "severity", "rule_name", "category")))
    if len(hits["cases"]) >= 2:
        return Guess("cases", DATA_TYPES["cases"], "medium",
                     [f"case-handling columns found: {', '.join(hits['cases'][:5])}"])
    if len(hits["assets"]) >= 1 and not alert_hits:
        return Guess("assets", DATA_TYPES["assets"], "medium",
                     [f"inventory columns found: {', '.join(hits['assets'][:5])}"])
    if hits["telemetry"] and not alert_hits:
        return Guess("telemetry", DATA_TYPES["telemetry"], "medium",
                     [f"volume columns found: {', '.join(hits['telemetry'][:5])}"])
    if alert_hits:
        conf = "high" if len(alert_hits) >= 2 else "medium"
        return Guess("alerts", DATA_TYPES["alerts"], conf,
                     [f"alert columns found: {', '.join(alert_hits[:6])}"])
    return Guess("alerts", DATA_TYPES["alerts"], "low",
                 ["no familiar column names; assuming one row per alert"])


def _text_sample(frames: list[pd.DataFrame], names: list[str], limit: int = 3000) -> str:
    parts = [" ".join(names)]
    for df in frames:
        cols = [c for c in df.columns if _key(c) in {
            "entityid", "orgid", "organization", "organisation", "tenant", "customer", "company", "name",
            "host", "hostname", "assetid", "asset", "device", "devicename", "computername", "rulename", "rule",
            "alerttitle", "title", "description", "signature", "category", "sector", "assettype", "agentname"}]
        for c in cols:
            vals = df[c].dropna().astype(str)
            parts.append(" ".join(vals.sample(min(limit, len(vals)), random_state=0) if len(vals) > limit else vals))
    return " ".join(parts).lower()


def _sector(frames: list[pd.DataFrame], names: list[str]) -> Guess:
    for df in frames:
        for c in df.columns:
            if _key(c) == "sector":
                v = df[c].dropna().astype(str).str.lower()
                if len(v) and v.mode().iat[0] in SECTORS:
                    return Guess(v.mode().iat[0], v.mode().iat[0].title(), "high",
                                 ["the data has a 'sector' column"])
    text = _text_sample(frames, names)
    tokens = re.findall(r"[a-z0-9]+", text)
    joined = " " + " ".join(tokens) + " "
    scores = {}
    found = {}
    for sector, words in SECTOR_KEYWORDS.items():
        hits = [w for w in words if f" {w} " in joined or (len(w) > 4 and w in joined)]
        n = sum(joined.count(f" {w} ") + (joined.count(w) if len(w) > 4 else 0) for w in hits)
        if n:
            scores[sector], found[sector] = n, hits
    if not scores:
        return Guess("other", "Other / not sure", "low",
                     ["no sector-specific words (like 'scada', 'bank', 'hospital') in names, hosts or rules"])
    best = max(scores, key=scores.get)
    ranked = sorted(scores.values(), reverse=True)
    conf = "medium" if len(ranked) == 1 or ranked[0] >= 2 * ranked[1] else "low"
    return Guess(best, best.title(), conf,
                 [f"words such as {', '.join(repr(w) for w in found[best][:4])} appear in the data"])


def _size(alerts: int, hosts: int | None) -> Guess:
    size = "small" if alerts < 5_000 else "medium" if alerts < 50_000 else "large"
    if hosts:
        by_hosts = "small" if hosts < 100 else "medium" if hosts < 300 else "large"
        size = max(size, by_hosts, key=SIZES.index)
    reason = f"{alerts:,} alert rows" + (f" across {hosts:,} hosts/assets" if hosts else "")
    rule = "small < 5,000 alerts or < 100 hosts; large ≥ 50,000 or ≥ 300"
    return Guess(size, size.title(), "low", [f"{reason} ({rule})"])


def detect(raw: dict[str, pd.DataFrame], extra: dict[str, pd.DataFrame], file_names: list[str]) -> Detection:
    frames = list(raw.values()) + list(extra.values())
    main = raw.get("alerts")
    if main is None and extra:
        main = max(extra.values(), key=len)
    if main is None and frames:
        main = max(frames, key=len)
    main = main if main is not None else pd.DataFrame()
    keys = {_key(c) for df in frames for c in df.columns}
    dtype = _data_type(raw, extra, keys)
    hosts = None
    host_col = next((c for c in main.columns if _key(c) in ALERT_ALIASES["asset_id"]), None)
    if host_col is not None:
        hosts = int(main[host_col].nunique())
    if "assets" in raw:
        hosts = len(raw["assets"])
    mapping = {}
    for c in main.columns:
        k = _key(c)
        for target, names in ALERT_ALIASES.items():
            if k == _key(target) or k in names:
                mapping[str(c)] = target
                break
    present = set(raw) | ({"alerts"} if extra else set())
    missing = [t for t in ("alerts", "cases", "escalations", "assets", "telemetry") if t not in present]
    preview = main.head(5).astype(str).to_dict("records") if len(main) else []
    return Detection(
        data_type=dtype, sector=_sector(frames, file_names), size=_size(len(main), hosts),
        rows=int(sum(len(f) for f in frames)), tables={k: len(v) for k, v in raw.items()} | {
            k: len(v) for k, v in extra.items()},
        columns=[str(c) for c in main.columns][:40], mapping=mapping, missing_for_full=missing, preview=preview)

