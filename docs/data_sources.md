# Data sources

| Dataset | Source | Licence | Raw size | Use |
|---|---|---|---|---|
| AIT Alert Data Set | Zenodo record 8263181 | CC-BY-4.0 | 96 MB zip → 2.7 GB NDJSON | Real IDS alerts (Wazuh, AMiner) from 8 simulated enterprise scenarios; alert-pattern clustering |
| Microsoft GUIDE | Kaggle `Microsoft/microsoft-security-incident-prediction` | See the Kaggle page (checked at download) | ~ several GB CSV | Real incident/alert triage records; benchmark sample of ~100k rows |
| Synthetic CSEs | `scripts/generate_synthetic.py` | Project-generated | 39 MB | Full entity / asset / alert / case / escalation / telemetry data with planted weaknesses and ground truth |

## AIT Alert Data Set
- Download: `python scripts/download_data.py ait` (MD5 checked against Zenodo).
- Convert: `python scripts/convert_ait.py` → `data/processed/ait/`
  - `wazuh_alerts.parquet`: 2,600,263 alerts (8 scenarios)
  - `aminer_alerts.parquet`: 55,558 alerts
  - `sample_alerts.parquet`: working sample of 4 scenarios (russellmitchell, santos, shaw, wardbeck), 338,362 alerts
- `attack_label` is set by attack time window from `labels.csv` (same scenario). This is approximate, because AIT's
  own labelling also uses the host.
- Conversion streams each file through DuckDB with a 4 GB memory limit and takes about 5 s.

## Microsoft GUIDE
- Download (Kaggle token required; pass it as the `KAGGLE_API_TOKEN` environment variable or put
  `kaggle.json` in `%USERPROFILE%\.kaggle\`; never in the repo): `python scripts/download_data.py guide`.
  Downloaded 2026-11-09: `GUIDE_Train.csv`, 2,425,409,087 bytes (size matches Kaggle's listing).
- Convert: `python scripts/convert_guide.py` → `data/processed/guide/`
  - `guide_train.parquet`: 9,516,837 rows = 1,265,644 alerts from 5,769 organisations (318 MB)
  - `sample_alerts.parquet`: working sample of 99,996 alerts from the 12 organisations with the most alerts
    (one row per AlertId; seeded per-org sample), 15 MITRE categories, 2023-12-29 → 2024-06-17
- Ingested by `scripts/ingest.py` **through the same automatic mapping a user's own export goes through**
  (OrgId → organisation, AlertTitle → rule, Category → category with MITRE names translated, DeviceId → asset).
  GUIDE has no severity, case timing or asset inventory, so it supports alert-level checks only
  (category coverage, volume, pattern clustering).

## Synthetic CSEs
`python scripts/generate_synthetic.py --seed 7` writes `data/raw/synthetic/CSEnn/` and
`data/processed/ground_truth.json`. Period: 2026-06-01 to 2026-08-31 (91 days).

Export formats are mixed on purpose: CSV (7 entities), JSON (3), SQLite (2).

Tables per entity: `entity`, `assets` (with `criticality`), `alerts` (category, severity, rule, source),
`cases` (assignee, opened/closed, SLA deadline, disposition, escalated flag, remediation, notes),
`escalations`, `telemetry` (daily event count per asset).

| Entity | Sector / size | Planted weaknesses |
|---|---|---|
| CSE01 | power / large | healthy |
| CSE02 | banking / large | fast_closure, critical_no_escalation |
| CSE03 | telecom / medium | template_notes |
| CSE04 | transport / medium | healthy |
| CSE05 | health / medium | repeated_no_remediation, silent_critical_assets |
| CSE06 | government / large | low_activity, missing_categories |
| CSE07 | power / medium | healthy |
| CSE08 | water / small | sla_gaming |
| CSE09 | banking / medium | missing_records (alerts without cases; escalations without records) |
| CSE10 | telecom / large | healthy |
| CSE11 | transport / small | fast_closure, template_notes, sla_gaming |
| CSE12 | power / small | silent_critical_assets, missing_categories |

Healthy entities still contain realistic noise (fast auto-closes of low-severity alerts, unescalated
false positives, open cases), so detectors cannot rely on trivially clean baselines.
