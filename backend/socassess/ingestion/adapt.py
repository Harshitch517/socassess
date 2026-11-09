"""Automatic mapping for data that does not follow the SOCAssess schema exactly.

Users often have "an alerts export" from their SIEM rather than six tidy tables. This module turns
such input into schema tables before validation, and says what it assumed:

* an unrecognised single file/table is treated as the alerts table;
* common column names are mapped (Timestamp -> ts, AlertTitle -> rule_name, OrgId -> entity_id, ...);
* severity is normalised from text (informational, warning, severe...) or numbers (1-4, 0-15, 0-100);
* missing alert ids, categories and entity ids are filled, and entities that are not known yet are
  created (sector "unknown", size from alert volume).

Data already in the schema passes through unchanged. Everything that cannot be inferred safely
(for example missing timestamps) is left for validation to reject with a clear message.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

# target column -> accepted source names (compared after lower-casing and removing non-alphanumerics)
ALERT_ALIASES: dict[str, list[str]] = {
    "ts": ["ts", "timestamp", "time", "datetime", "date", "eventtime", "createdat", "created", "firstseen",
           "detectiontime", "alerttime", "generatedtime", "timegenerated", "eventtimestamp", "logtime"],
    "severity": ["severity", "severitylevel", "priority", "level", "rulelevel", "risk", "risklevel", "criticality",
                 "alertseverity", "urgency"],
    "category": ["category", "alertcategory", "type", "alerttype", "tactic", "attacktype", "classification",
                 "threatcategory", "eventtype", "attackcat", "group", "rulegroup", "rulegroups", "mitretactic"],
    "rule_name": ["rulename", "rule", "alerttitle", "title", "alertname", "signature", "signaturename",
                  "description", "detectionname", "name", "message", "ruledescription"],
    "asset_id": ["assetid", "asset", "host", "hostname", "deviceid", "device", "devicename", "computer",
                 "computername", "endpoint", "srcip", "sourceip", "ip", "agentname"],
    "alert_id": ["alertid", "id", "eventid", "uid", "uuid", "alertuuid", "recordid"],
    "entity_id": ["entityid", "orgid", "org", "organization", "organisation", "tenant", "tenantid", "customer",
                  "customerid", "company", "entity", "cse", "site"],
    "case_id": ["caseid", "case", "incidentid", "ticketid", "ticket", "incident"],
    "source": ["source", "detector", "product", "sensor", "tool", "detectionsource", "logsource"],
}

SEVERITY_WORDS = {
    "low": ["low", "info", "informational", "information", "minor", "lowest", "notice", "debug", "l", "p4", "p5"],
    "medium": ["medium", "med", "moderate", "warning", "warn", "m", "p3", "normal"],
    "high": ["high", "major", "error", "important", "h", "p2", "severe"],
    "critical": ["critical", "crit", "emergency", "alert", "fatal", "highest", "c", "p1", "p0", "very high"],
}
_WORD_TO_SEV = {w: s for s, ws in SEVERITY_WORDS.items() for w in ws}

# Category synonyms -> the vocabulary used by peers, so different naming isn't mistaken for a gap.
# MITRE ATT&CK tactic names (as used by e.g. Microsoft GUIDE) are included.
CATEGORY_SYNONYMS = {
    "brute_force": ["bruteforce", "brute_force_attack", "password_spray", "password_guessing", "credential_access",
                    "failed_login", "login_failure", "authentication_failure", "auth_failure"],
    "recon": ["reconnaissance", "discovery", "scan", "scanning", "port_scan", "network_scan", "enumeration"],
    "malware": ["virus", "trojan", "ransomware", "worm", "malicious_file", "execution"],
    "phishing": ["phish", "email_threat", "spam", "spearphishing", "malicious_email"],
    "policy_violation": ["policy", "compliance", "acceptable_use", "policy_breach"],
    "lateral_movement": ["lateralmovement"],
    "privilege_escalation": ["privilegeescalation", "privesc", "privilege_abuse"],
    "data_exfiltration": ["exfiltration", "data_loss", "dlp", "data_leak", "exfil"],
    "ics_anomaly": ["ics", "ot", "scada", "ot_anomaly", "ics_attack"],
}
_CAT_SYN = {s: c for c, ss in CATEGORY_SYNONYMS.items() for s in ss}


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _map_columns(df: pd.DataFrame, aliases: dict[str, list[str]], notes: list[str]) -> tuple[pd.DataFrame, set]:
    keys = {_key(c): c for c in df.columns}
    rename = {}
    for target, names in aliases.items():
        if target in df.columns:
            continue
        for n in names:
            src = keys.get(n)
            if src is not None and src not in rename and src not in aliases:
                rename[src] = target
                break
    if rename:
        notes.append("mapped columns: " + ", ".join(f"{s} → {t}" for s, t in rename.items()))
    return df.rename(columns=rename), set(rename.values())


def normalise_severity(s: pd.Series, notes: list[str], lenient: bool = True) -> pd.Series:
    """Map any reasonable severity encoding to low/medium/high/critical.

    lenient=False (schema uploads): synonyms are translated but unknown values are kept, so
    validation rejects them instead of silently turning a typo into 'medium'."""
    txt = s.astype("string").str.strip().str.lower()
    if txt.dropna().isin(list(SEVERITY_WORDS)).all():
        return txt
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().mean() > 0.9:
        hi = float(num.max())
        if hi <= 4:
            cuts, scale = [1, 2, 3], "1-4"
        elif hi <= 10:
            cuts, scale = [3, 6, 8], "0-10"
        elif hi <= 15:
            cuts, scale = [3, 7, 11], "0-15 (Wazuh-style)"
        else:
            cuts, scale = [25, 50, 75], "0-100"
        out = pd.Series(np.select([num <= cuts[0], num <= cuts[1], num <= cuts[2]], ["low", "medium", "high"],
                                  "critical"), index=s.index).where(num.notna(), "medium")
        notes.append(f"severity: numeric values read on a {scale} scale")
        return out
    mapped = txt.astype(object).map(lambda v: _WORD_TO_SEV.get(v) if isinstance(v, str) else None).astype(object)
    unknown = sorted(set(txt[mapped.isna() & txt.notna()].unique()))[:8]
    if not lenient:
        translated = int((mapped.notna() & (mapped != txt)).sum())
        if translated:
            notes.append(f"severity: {translated:,} values translated (e.g. 'informational' → 'low')")
        return mapped.where(mapped.notna(), s.astype(object))
    if unknown:
        notes.append(f"severity: unrecognised values {unknown} set to 'medium'")
    return mapped.fillna("medium")


def _size_for(n_alerts: int) -> str:
    return "small" if n_alerts < 5_000 else "medium" if n_alerts < 50_000 else "large"


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").upper()[:40] or "UPLOAD"


def adapt(raw: dict[str, pd.DataFrame], extra: dict[str, pd.DataFrame], *, known_entities: set[str],
          default_entity: str, sector: str | None = None, size: str | None = None
          ) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Return (tables ready for validation, notes describing every assumption made)."""
    notes: list[str] = []
    raw = dict(raw)
    if "alerts" not in raw and extra:
        origin, df = max(extra.items(), key=lambda kv: len(kv[1]))
        raw["alerts"] = df
        notes.append(f"'{origin}' treated as the alerts table ({len(df):,} rows)")
        if len(extra) > 1:
            notes.append("other unrecognised files ignored: " + ", ".join(k for k in extra if k != origin))
    if "alerts" not in raw:
        return raw, notes

    a, mapped = _map_columns(raw["alerts"].copy(), ALERT_ALIASES, notes)
    entity_default = _slug(default_entity)
    if "entity_id" not in a.columns or a["entity_id"].isna().all():
        a["entity_id"] = entity_default
        notes.append(f"no organisation column: all rows assigned to entity '{entity_default}'")
    else:
        a["entity_id"] = a["entity_id"].astype("string").str.strip()
        if a["entity_id"].isna().any():
            a["entity_id"] = a["entity_id"].fillna(entity_default)
            notes.append(f"rows without an organisation assigned to '{entity_default}'")
    if "severity" in a.columns:
        a["severity"] = normalise_severity(a["severity"], notes, lenient="severity" in mapped)
    else:
        a["severity"] = "medium"
        notes.append("no severity column: all alerts set to 'medium' (severity-based checks are less informative)")
    if "category" not in a.columns:
        a["category"] = "uncategorized"
        notes.append("no category column: alerts set to 'uncategorized' (category coverage cannot be checked)")
    else:
        cat = (a["category"].astype("string").str.strip()
               .str.replace(r"(?<=[a-z])(?=[A-Z])", "_", regex=True)  # InitialAccess -> initial_access
               .str.lower().str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_").fillna("uncategorized"))
        canon = cat.map(lambda c: _CAT_SYN.get(c, c))
        changed = sorted({f"{x} → {y}" for x, y in zip(cat, canon, strict=True) if x != y})
        if changed:
            notes.append("categories renamed to the common vocabulary: " + ", ".join(changed[:10]))
        a["category"] = canon
    if "alert_id" not in a.columns:
        a["alert_id"] = [f"{e}-U{i:07d}" for i, e in enumerate(a["entity_id"])]
        notes.append("no alert id column: ids generated")
    else:
        a["alert_id"] = a["alert_id"].astype("string")
        dup = a["alert_id"].duplicated(keep=False)
        if dup.any() and "alert_id" in mapped:  # schema uploads keep duplicates so validation reports them
            # e.g. GUIDE repeats an AlertId once per evidence row: keep the first row of each alert
            a = a[~a["alert_id"].duplicated(keep="first")]
            notes.append(f"{int(dup.sum()):,} rows shared an alert id; kept the first row of each alert")
    if "asset_id" in mapped:  # foreign host names are only unique within one organisation
        a["asset_id"] = a["entity_id"].astype(str) + ":" + a["asset_id"].astype("string").fillna("unknown")
    raw["alerts"] = a

    if "entities" not in raw:
        new = sorted(set(a["entity_id"].dropna()) - known_entities)
        if new:
            counts = a.groupby("entity_id").size()
            raw["entities"] = pd.DataFrame({
                "entity_id": new, "name": [default_entity if e == entity_default else f"Organisation {e}" for e in new],
                "sector": sector or "unknown",
                "size": [size or _size_for(int(counts.get(e, 0))) for e in new],
                "source": None})  # filled by the pipeline's `source` (upload, guide, ...)
            notes.append(f"created {len(new)} entit{'y' if len(new) == 1 else 'ies'} (sector '{sector or 'unknown'}', "
                         f"size {size or 'from alert volume'})")
    return raw, notes
