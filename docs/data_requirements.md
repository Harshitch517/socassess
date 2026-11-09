# Data requirements

What a CSE must submit, and what each detector needs. The exact schema (columns, types, aliases and
validation rules) is in `data_schema.md`.

## Minimum submission
| Table | Required | Purpose |
|---|---|---|
| `entities` | yes (first upload) | Name, sector, size: used for peer groups |
| `alerts` | yes | id, timestamp, category, severity; ideally asset_id, rule_name, case_id |
| `cases` | strongly recommended | Assignee, opened/closed time, SLA deadline, status, disposition, escalated flag, remediation, notes |
| `escalations` | recommended | One row per escalation actually raised |
| `assets` | recommended | Inventory with **criticality** (low/medium/high/critical) and type |
| `telemetry` | recommended | Daily event count per asset (log volume) |

## Detector → data dependency
| Detector | alerts | cases | escalations | assets | telemetry |
|---|:-:|:-:|:-:|:-:|:-:|
| Fast closure | ● | ● | | | |
| Critical not escalated | ● | ● | | ○ | |
| Copy-paste notes | | ● (notes) | | | |
| Repeat alerts, no fix | ● (asset_id, rule) | ● (remediation) | | ○ | |
| SLA bunching / breaches | | ● (sla_deadline) | | | |
| Silent critical assets | ○ | | | ● | ● |
| Missing categories | ● | | | | |
| Missing records | ● | ● | ● | | |
| Low activity | ● | | | ● | ○ |
| Anomaly / benchmarks | ● | ● | ○ | ○ | ○ |

● required · ○ used when present. A missing table produces a warning on upload, and the detectors
that need it are skipped for that entity. Nothing fails.

## Volume and period
- Recommended submission period: one month to one quarter. Trends are weekly.
- Rate-based detectors need at least **30 relevant cases** per entity (`min_cases`) to judge an entity.
- Peer comparison needs **3 or more entities of the same source**; IsolationForest needs **8 or more**.
- Re-uploading the same records is safe (upsert by primary key). A new period simply adds rows.

## Data quality rules (enforced on upload)
Rejected, with table/column/row named: missing required columns or values, invalid enums, bad timestamps,
duplicate ids, unknown entity, `closed_at` before `opened_at`, a closed case without `closed_at`, and
escalations for unknown cases. Accepted on purpose: alerts without cases, and escalated cases without
escalation records. These are evidence, not errors.

## Privacy
Only operational metadata is needed. Hostnames, analyst ids and note text can be pseudonymised by the CSE
before submission; detectors only compare values for equality and similarity, so consistent pseudonyms
work unchanged. Data never leaves the machine running SOCAssess.

## Datasets used in this project
| Dataset | Use | Licence |
|---|---|---|
| Synthetic CSEs (`generate_synthetic.py`) | Full-schema demo and validation with ground truth | Project-generated |
| AIT Alert Data Set (Zenodo 8263181) | Real IDS alerts for pattern clustering (4 scenarios ingested) | CC-BY-4.0 |
| Microsoft GUIDE (Kaggle) | Planned real triage sample (needs the user's Kaggle token) | See the Kaggle page |
