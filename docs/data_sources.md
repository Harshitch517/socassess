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
- Needs a Kaggle API token at `%USERPROFILE%\.kaggle\kaggle.json` (never stored in the repo).
- Download: `python scripts/download_data.py guide`. **Pending: waiting for the user's token.**

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
