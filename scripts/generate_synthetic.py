"""Generate synthetic CSE (critical-sector entity) SOC data with planted weaknesses.

    python scripts/generate_synthetic.py [--seed 7] [--out data/raw/synthetic]

For each of 12 fictional entities this writes one export folder holding
entity / assets / alerts / cases / escalations / telemetry. The export format differs per
entity (csv, json or sqlite), as real CSE submissions would. The planted weaknesses, with
the ids of the records that show them, go to data/processed/ground_truth.json and are later
used to measure the detectors' precision and recall.

Weakness types (ground-truth `type` values):
  fast_closure             high/critical cases closed within minutes
  critical_no_escalation   critical true positives closed without escalation
  template_notes           copy-paste investigation notes
  repeated_no_remediation  same rule firing again and again on one asset with no fix
  silent_critical_assets   critical assets with no or almost no telemetry
  missing_categories       expected alert categories absent compared with peers
  low_activity             alert volume far below peers of the same size
  sla_gaming               closures bunched just before the SLA deadline
  missing_records          alerts without cases; escalated cases without escalation records
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PERIOD_START = datetime(2026, 6, 1, tzinfo=UTC)
DAYS = 91
PERIOD_END = PERIOD_START + timedelta(days=DAYS)

SIZE = {  # assets, alerts/day, analysts
    "small": (60, 20, 3),
    "medium": (150, 50, 6),
    "large": (400, 120, 12),
}
SLA_HOURS = {"critical": 4, "high": 8, "medium": 24, "low": 72}
SEVERITIES = ["low", "medium", "high", "critical"]

CATEGORIES = {  # category: (weight, severity probabilities low/med/high/crit, rule names)
    "malware": (14, [0.15, 0.35, 0.35, 0.15],
                ["EDR malware detection", "Suspicious PowerShell download", "Ransomware behaviour"]),
    "phishing": (16, [0.30, 0.45, 0.20, 0.05],
                 ["Phishing URL clicked", "Malicious attachment opened", "Credential phish reported"]),
    "brute_force": (14, [0.30, 0.40, 0.25, 0.05],
                    ["Multiple failed logons", "SSH brute force", "Password spray detected"]),
    "recon": (16, [0.55, 0.35, 0.08, 0.02],
              ["Port scan detected", "Directory enumeration", "LDAP reconnaissance"]),
    "policy_violation": (18, [0.60, 0.30, 0.08, 0.02],
                         ["USB storage connected", "Unapproved software", "Admin share access"]),
    "lateral_movement": (7, [0.05, 0.25, 0.45, 0.25],
                         ["PsExec remote execution", "Pass-the-hash suspected", "RDP from server"]),
    "privilege_escalation": (6, [0.05, 0.20, 0.45, 0.30],
                             ["New domain admin", "Sudo abuse", "Token manipulation"]),
    "data_exfiltration": (5, [0.05, 0.20, 0.40, 0.35],
                          ["Large outbound transfer", "DNS tunnelling", "Cloud upload anomaly"]),
    "ics_anomaly": (4, [0.10, 0.30, 0.35, 0.25],
                    ["Unexpected Modbus write", "PLC program change", "HMI login off-hours"]),
}
ICS_SECTORS = {"power", "transport", "water"}

ASSET_TYPES = [  # type, share, critical probability, telemetry median events/day
    ("workstation", 0.55, 0.00, 800),
    ("server", 0.20, 0.10, 5000),
    ("database", 0.06, 0.70, 8000),
    ("web_server", 0.06, 0.30, 12000),
    ("domain_controller", 0.03, 1.00, 20000),
    ("firewall", 0.04, 0.60, 50000),
    ("mail_server", 0.03, 0.50, 15000),
    ("scada_hmi", 0.03, 1.00, 3000),  # ICS sectors only
]

DISPOSITIONS = ["true_positive", "false_positive", "benign", "duplicate"]
DISP_P = [0.22, 0.48, 0.24, 0.06]
ESC_TARGETS = ["Internal IR team", "CISO", "CERT-In", "NCIIPC"]
REMEDIATIONS = ["host isolated", "malware removed", "account disabled", "IOC blocked on firewall",
                "patch applied", "host reimaged", "credentials reset", "rule tuned"]


@dataclass
class Spec:
    entity_id: str
    name: str
    sector: str
    size: str
    region: str
    fmt: str
    weaknesses: list[str] = field(default_factory=list)


SPECS = [
    Spec("CSE01", "Northgrid Power Corp", "power", "large", "North", "csv"),
    Spec("CSE02", "Meridian Bank", "banking", "large", "West", "csv",
         ["fast_closure", "critical_no_escalation"]),
    Spec("CSE03", "TelLink Networks", "telecom", "medium", "South", "json", ["template_notes"]),
    Spec("CSE04", "Railway Signalling Board", "transport", "medium", "East", "csv"),
    Spec("CSE05", "State Health Network", "health", "medium", "Central", "sqlite",
         ["repeated_no_remediation", "silent_critical_assets"]),
    Spec("CSE06", "Government Data Centre", "government", "large", "North", "csv",
         ["low_activity", "missing_categories"]),
    Spec("CSE07", "Coastal Power Utility", "power", "medium", "South", "json"),
    Spec("CSE08", "Urban Water Authority", "water", "small", "West", "csv", ["sla_gaming"]),
    Spec("CSE09", "Capital Payments Ltd", "banking", "medium", "West", "sqlite",
         ["missing_records"]),
    Spec("CSE10", "Metro Telecom", "telecom", "large", "East", "csv"),
    Spec("CSE11", "Eastern Port Authority", "transport", "small", "East", "csv",
         ["fast_closure", "template_notes", "sla_gaming"]),
    Spec("CSE12", "Regional Grid Operator", "power", "small", "Central", "json",
         ["silent_critical_assets", "missing_categories"]),
]

TEMPLATE_NOTES = [
    "Alert reviewed. No malicious activity observed. Closing as false positive.",
    "Alert reviewed. No malicious activity observed. Closing as false positive",
    "alert reviewed. no malicious activity observed. closing as false positive.",
    "Alert reviewed - no malicious activity observed. Closing as false positive.",
]
PROCS = ["powershell.exe", "cmd.exe", "rundll32.exe", "svchost.exe", "python3", "bash", "wmic.exe",
         "certutil.exe", "sshd", "java", "outlook.exe", "chrome.exe"]
USERS = ["svc_backup", "j.rao", "a.mehta", "admin_ops", "s.khan", "r.iyer", "svc_web", "p.nair",
         "k.das", "m.singh", "t.verma", "guest01"]
FINDINGS = {
    "true_positive": ["Confirmed malicious {proc} activity by {user}",
                      "Verified compromise indicators: {n} connections to {ip}",
                      "Payload hash matched threat intel feed; {proc} spawned from {user} session"],
    "false_positive": ["Activity traced to scheduled job run by {user}",
                       "{proc} execution matches approved admin script",
                       "Connections to {ip} belong to vendor update server",
                       "Spike of {n} events explained by change ticket CHG{t}"],
    "benign": ["Expected behaviour for {user}; confirmed with asset owner",
               "Vulnerability scanner {ip} generated {n} events",
               "User {user} confirmed the login from new device"],
    "duplicate": ["Duplicate of earlier case on the same host; merged",
                  "Same {proc} event already tracked in previous case"],
}
ACTIONS = ["Checked EDR timeline for {h}h before and after.", "Reviewed proxy and DNS logs.",
           "Pulled process tree and parent command line.", "Correlated with firewall logs for {ip}.",
           "Contacted asset owner by phone.", "Queried SIEM for other hosts with same indicator.",
           "Compared with baseline for this host."]


def _ip(rng) -> str:
    return f"10.{rng.integers(0, 255)}.{rng.integers(0, 255)}.{rng.integers(1, 254)}"


def _note(rng, host: str, rule: str, disposition: str, remediation: str | None) -> str:
    fill = dict(proc=rng.choice(PROCS), user=rng.choice(USERS), ip=_ip(rng),
                n=int(rng.integers(3, 900)), t=int(rng.integers(10000, 99999)),
                h=int(rng.integers(1, 48)))
    parts = [f"Investigated '{rule}' on {host}."]
    parts += [a.format(**fill) for a in rng.choice(ACTIONS, size=rng.integers(1, 3), replace=False)]
    parts.append(rng.choice(FINDINGS[disposition]).format(**fill) + ".")
    if remediation:
        parts.append(f"Remediation: {remediation}.")
    return " ".join(parts)


def _iso(dt: datetime | None) -> str | None:
    return None if dt is None or pd.isna(dt) else dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_entity(spec: Spec, rng: np.random.Generator) -> tuple[dict, dict]:
    """Return (tables, ground-truth entry) for one entity."""
    n_assets, per_day, n_analysts = SIZE[spec.size]
    w = set(spec.weaknesses)
    truth: dict[str, dict] = {}

    # Assets
    types = [t for t in ASSET_TYPES if t[0] != "scada_hmi" or spec.sector in ICS_SECTORS]
    shares = np.array([t[1] for t in types])
    shares /= shares.sum()
    picks = rng.choice(len(types), size=n_assets, p=shares)
    assets = []
    for i, k in enumerate(picks):
        atype, _, pcrit, _ = types[k]
        crit = rng.random() < pcrit
        assets.append(dict(asset_id=f"{spec.entity_id}-A{i:04d}", entity_id=spec.entity_id,
                           hostname=f"{spec.entity_id.lower()}-{atype.replace('_', '')}-{i:03d}",
                           asset_type=atype,
                           criticality="critical" if crit else rng.choice(
                               ["high", "medium", "low"], p=[0.2, 0.5, 0.3]),
                           owner_team=rng.choice(["IT Ops", "Network", "OT Ops", "AppDev"])))
    assets_df = pd.DataFrame(assets)
    crit_ids = assets_df.loc[assets_df.criticality == "critical", "asset_id"].tolist()

    silent: set[str] = set()
    if "silent_critical_assets" in w:
        silent = set(rng.choice(crit_ids, size=max(3, len(crit_ids) // 4), replace=False))
        truth["silent_critical_assets"] = dict(evidence_ids=sorted(silent))

    # Telemetry: daily event counts per asset; silent assets drop to ~0
    tel = []
    median = {t[0]: t[3] for t in ASSET_TYPES}
    for a in assets:
        base = median[a["asset_type"]] * rng.lognormal(0, 0.3)
        counts = rng.poisson(base * rng.lognormal(0, 0.15, DAYS))
        if a["asset_id"] in silent:
            stop = int(rng.integers(0, DAYS // 3))  # went quiet early in the period
            counts[stop:] = rng.binomial(1, 0.03, DAYS - stop) * rng.integers(1, 5, DAYS - stop)
        for d in range(DAYS):
            tel.append((spec.entity_id, a["asset_id"], (PERIOD_START + timedelta(days=d)).date(),
                        int(counts[d])))
    telemetry_df = pd.DataFrame(tel, columns=["entity_id", "asset_id", "date", "event_count"])

    # Alerts
    cats = [c for c in CATEGORIES if c != "ics_anomaly" or spec.sector in ICS_SECTORS]
    if "missing_categories" in w:
        missing = ["ics_anomaly"] if spec.sector in ICS_SECTORS and spec.size == "small" \
            else ["lateral_movement", "privilege_escalation"]
        if spec.sector in ICS_SECTORS:
            missing = sorted(set(missing) | {"ics_anomaly"})
        cats = [c for c in cats if c not in missing]
        truth["missing_categories"] = dict(evidence_ids=[], categories=missing)
    cw = np.array([CATEGORIES[c][0] for c in cats], float)
    cw /= cw.sum()
    rate = per_day * (0.14 if "low_activity" in w else rng.uniform(0.85, 1.15))
    if "low_activity" in w:
        truth["low_activity"] = dict(evidence_ids=[], volume_factor=0.14)
    n_alerts = int(rate * DAYS)
    live = assets_df[~assets_df.asset_id.isin(silent)]
    aw = np.where(live.criticality == "critical", 2.0, 1.0)
    aw /= aw.sum()
    hours = np.array([1, 1, 1, 1, 1, 2, 3, 5, 7, 8, 8, 8, 7, 8, 8, 8, 7, 6, 4, 3, 2, 2, 1, 1], float)
    hours /= hours.sum()

    def make_alert(ts, cat, sev, asset_row, rule=None):
        return dict(entity_id=spec.entity_id, asset_id=asset_row.asset_id, ts=ts, category=cat,
                    severity=sev, rule_name=rule or rng.choice(CATEGORIES[cat][2]),
                    source=rng.choice(["EDR", "SIEM", "IDS", "Firewall"]))

    alerts = []
    for _ in range(n_alerts):
        ts = PERIOD_START + timedelta(days=int(rng.integers(0, DAYS)),
                                      hours=int(rng.choice(24, p=hours)),
                                      seconds=int(rng.integers(0, 3600)))
        cat = rng.choice(cats, p=cw)
        sev = rng.choice(SEVERITIES, p=CATEGORIES[cat][1])
        alerts.append(make_alert(ts, cat, sev, live.iloc[rng.choice(len(live), p=aw)]))

    repeat_assets: set[str] = set()
    if "repeated_no_remediation" in w:
        targets = live.sample(4, random_state=int(rng.integers(1 << 30)))
        for _, row in targets.iterrows():
            cat = rng.choice(["malware", "brute_force"])
            rule = CATEGORIES[cat][2][0]
            for _ in range(int(rng.integers(25, 40))):
                ts = PERIOD_START + timedelta(seconds=int(rng.integers(0, DAYS * 86400)))
                alerts.append(make_alert(ts, cat, rng.choice(["medium", "high"], p=[.4, .6]),
                                         row, rule) | {"_repeat": True})
            repeat_assets.add(row.asset_id)

    alerts.sort(key=lambda a: a["ts"])
    for i, a in enumerate(alerts):
        a["alert_id"] = f"{spec.entity_id}-AL{i:06d}"

    # Cases and escalations
    analysts = [f"{spec.entity_id.lower()}.analyst{j:02d}" for j in range(n_analysts)]
    template_analysts = set(analysts[:2]) if "template_notes" in w else set()
    hostname = dict(zip(assets_df.asset_id, assets_df.hostname, strict=True))
    cases, escs = [], []
    ev = {k: [] for k in ("fast_closure", "critical_no_escalation", "template_notes",
                          "repeated_no_remediation", "sla_gaming", "missing_records")}
    for a in alerts:
        sev = a["severity"]
        if "missing_records" in w and sev in ("high", "critical") and rng.random() < 0.18:
            a["case_id"] = None
            ev["missing_records"].append(a["alert_id"])
            continue
        case_id = a["alert_id"].replace("-AL", "-CS")
        a["case_id"] = case_id
        opened = a["ts"] + timedelta(minutes=float(rng.exponential(12)))
        sla = timedelta(hours=SLA_HOURS[sev])
        deadline = opened + sla
        disp = rng.choice(DISPOSITIONS, p=DISP_P)
        if a.get("_repeat"):
            disp = rng.choice(["false_positive", "benign"])
        ttc = timedelta(hours=SLA_HOURS[sev] * 0.3 * float(rng.lognormal(0, 0.8)))
        tag = None
        if "fast_closure" in w and sev in ("high", "critical") and rng.random() < 0.45:
            ttc = timedelta(seconds=float(rng.uniform(30, 240)))
            disp = rng.choice(["false_positive", "benign"], p=[0.7, 0.3])
            tag = "fast_closure"
        elif "sla_gaming" in w and sev in ("medium", "high") and rng.random() < 0.6:
            ttc = sla - timedelta(seconds=float(rng.uniform(60, 0.03 * sla.total_seconds())))
            tag = "sla_gaming"
        closed = opened + ttc
        status = "closed"
        if closed > PERIOD_END:
            closed, status = None, "open"
        assignee = rng.choice(analysts)
        escalate = disp == "true_positive" and (
            sev == "critical" and rng.random() < 0.95 or sev == "high" and rng.random() < 0.5)
        if "critical_no_escalation" in w and sev == "critical" and disp == "true_positive" \
                and rng.random() < 0.85:
            escalate = False
            if status == "closed":
                ev["critical_no_escalation"].append(case_id)
        remediation = rng.choice(REMEDIATIONS) if disp == "true_positive" else None
        if assignee in template_analysts and rng.random() < 0.75:
            note = rng.choice(TEMPLATE_NOTES)
            ev["template_notes"].append(case_id)
        else:
            note = _note(rng, hostname[a["asset_id"]], a["rule_name"], disp, remediation)
        if tag and status == "closed":
            ev[tag].append(case_id)
        if a.get("_repeat") and status == "closed":
            ev["repeated_no_remediation"].append(case_id)
        cases.append(dict(case_id=case_id, entity_id=spec.entity_id, alert_id=a["alert_id"],
                          assignee=assignee, opened_at=opened, closed_at=closed,
                          sla_deadline=deadline, status=status, disposition=disp,
                          escalated=bool(escalate), remediation=remediation, notes=note))
        if escalate:
            if "missing_records" in w and rng.random() < 0.5:
                ev["missing_records"].append(case_id)  # flagged escalated, no record kept
            else:
                escs.append(dict(escalation_id=case_id.replace("-CS", "-ES"), case_id=case_id,
                                 entity_id=spec.entity_id,
                                 escalated_at=opened + ttc * float(rng.uniform(0.1, 0.6)),
                                 escalated_to=rng.choice(ESC_TARGETS, p=[.5, .25, .15, .1]),
                                 reason=f"{sev} {a['category']} confirmed"))
    for k, ids in ev.items():
        if k in w:
            truth[k] = dict(evidence_ids=ids) | {kk: vv for kk, vv in truth.get(k, {}).items()
                                                 if kk != "evidence_ids"}
    if "repeated_no_remediation" in w:
        truth["repeated_no_remediation"]["assets"] = sorted(repeat_assets)

    alerts_df = pd.DataFrame([{k: v for k, v in a.items() if k != "_repeat"} for a in alerts])
    cases_df = pd.DataFrame(cases)
    esc_df = pd.DataFrame(escs, columns=["escalation_id", "case_id", "entity_id", "escalated_at",
                                         "escalated_to", "reason"])
    for df, cols in ((alerts_df, ["ts"]), (cases_df, ["opened_at", "closed_at", "sla_deadline"]),
                     (esc_df, ["escalated_at"])):
        for c in cols:
            df[c] = df[c].map(_iso)
    telemetry_df["date"] = telemetry_df["date"].astype(str)
    entity = dict(entity_id=spec.entity_id, name=spec.name, sector=spec.sector, size=spec.size,
                  region=spec.region, period_start=_iso(PERIOD_START), period_end=_iso(PERIOD_END),
                  export_format=spec.fmt)
    tables = dict(entity=pd.DataFrame([entity]), assets=assets_df, alerts=alerts_df,
                  cases=cases_df, escalations=esc_df, telemetry=telemetry_df)
    gt = dict(name=spec.name, sector=spec.sector, size=spec.size, healthy=not spec.weaknesses,
              weaknesses=[dict(type=k, **truth[k]) for k in spec.weaknesses])
    return tables, gt


def write_export(tables: dict[str, pd.DataFrame], folder: Path, fmt: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():
        old.unlink()
    if fmt == "csv":
        for name, df in tables.items():
            df.to_csv(folder / f"{name}.csv", index=False)
    elif fmt == "json":
        for name, df in tables.items():
            df.to_json(folder / f"{name}.json", orient="records", indent=None)
    elif fmt == "sqlite":
        with sqlite3.connect(folder / "export.sqlite") as con:
            for name, df in tables.items():
                df.to_sql(name, con, index=False)
        con.close()
    else:
        raise ValueError(fmt)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "raw" / "synthetic")
    ap.add_argument("--truth", type=Path, default=ROOT / "data" / "processed" / "ground_truth.json")
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    truth = dict(seed=args.seed, period_start=_iso(PERIOD_START), period_end=_iso(PERIOD_END),
                 sla_hours=SLA_HOURS, entities={})
    for spec in SPECS:
        tables, gt = build_entity(spec, rng)
        write_export(tables, args.out / spec.entity_id, spec.fmt)
        truth["entities"][spec.entity_id] = gt
        summary = ", ".join(f"{w['type']}({len(w['evidence_ids'])})" for w in gt["weaknesses"])
        print(f"{spec.entity_id} {spec.fmt:6} alerts={len(tables['alerts']):6,} "
              f"cases={len(tables['cases']):6,} esc={len(tables['escalations']):4} "
              f"assets={len(tables['assets']):3}  {summary or 'healthy'}")
    args.truth.parent.mkdir(parents=True, exist_ok=True)
    args.truth.write_text(json.dumps(truth, indent=1))
    print(f"ground truth -> {args.truth}")


if __name__ == "__main__":
    main()
