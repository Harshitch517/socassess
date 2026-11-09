# SOCAssess: supervisory analytics for SOC assessment

SIH 2026 · NCIIPC problem statement. SOCAssess ingests SOC alert and case-management data from many
critical-sector entities (CSEs), finds **execution gaps** (work done badly) and **negative space**
(work or telemetry that is missing), scores each entity's risk transparently, tells a supervisor
**exactly which records to review**, and explains every finding with evidence.
It is 100% free and open-source, with no external AI APIs, and runs fully offline.

## Results (synthetic validation, 5 seeds, 4 held out)
- **70/70** planted weaknesses detected, **0** false findings, **0/20** healthy entities flagged.
- All weaknesses are confirmed after reviewing about **54 records (≈4.5 h)**. Random sampling of the same 54 confirms 22–33%,
  and even 3,840 records (≈320 h) plateaus at 64%. Details: [docs/validation_report.md](docs/validation_report.md).

## Quick start

**Docker (offline, recommended)**
```bash
docker compose up -d --build      # then open http://localhost:8000
```
The image contains the UI, the API and a seeded demo of 12 synthetic CSEs. Upload your own exports on the *Data upload* page.

**Native (development)**
```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python scripts/generate_synthetic.py        # demo CSEs + ground truth
.venv/Scripts/python scripts/ingest.py --fresh            # (+ AIT sample if downloaded)
.venv/Scripts/python scripts/run_analysis.py
.venv/Scripts/python -m uvicorn socassess.api.app:app --app-dir backend --port 8000
cd frontend && npm install && npm run dev                 # http://localhost:5173
```
Optional real data: `python scripts/download_data.py ait && python scripts/convert_ait.py`.

## What it finds
Fast closures · critical incidents not escalated · copy-paste investigation notes · repeated alerts with no
root-cause fix · closures bunched at the SLA deadline · SLA breaches · silent critical assets · missing alert
categories vs peers · missing case/escalation records · abnormally low activity · unusual operating profile
(IsolationForest with readable drivers) · recurring alert-pattern clusters (HDBSCAN) · weekly trends.

## Documentation
| Doc | Content |
|---|---|
| [architecture](docs/architecture.md) | Components, data flow, code map |
| [functional design](docs/functional_design.md) | Users, workflow, pages, requirements |
| [analytics methodology](docs/analytics_methodology.md) | Every detector, scoring and queue in detail |
| [model details](docs/model_details.md) | ML components, hardware, offline update, explainability, auditability |
| [data requirements](docs/data_requirements.md) · [data schema](docs/data_schema.md) · [data sources](docs/data_sources.md) | What CSEs submit; validation rules; datasets and licences |
| [infrastructure](docs/infrastructure.md) · [deployment](docs/deployment.md) | Sizing, offline install, security, public demo |
| [API](docs/api.md) | Endpoints and settings |
| [validation report](docs/validation_report.md) | Precision/recall and the manual-sampling comparison |
| `PROGRESS.md` · `DECISIONS.md` | Stage log and design decisions |

## Tests
`.venv/Scripts/python -m pytest -q` runs 72 tests: ingestion, every detector, scoring, API, validation maths.
`cd frontend && npm run build` typechecks and builds the UI.
