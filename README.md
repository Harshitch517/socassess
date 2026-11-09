# SOCAssess

Supervisory analytics for SOC assessment (SIH 2026, NCIIPC). It ingests SOC alert and
case-management data from many organisations (CSEs), finds execution gaps and negative space,
scores each entity's risk, ranks what a human supervisor should review, and explains every
finding with evidence. The core runs fully offline and uses only free, open-source tools.

## Layout
| Path | Purpose |
|---|---|
| `backend/socassess/` | Python package: ingestion, analytics engine, FastAPI app |
| `frontend/` | React + Vite + TypeScript UI (Stage 5) |
| `data/raw/` | Downloaded datasets (not committed) |
| `data/processed/` | Parquet, DuckDB, `ground_truth.json` |
| `scripts/` | Download, conversion and synthetic-data scripts |
| `tests/` | pytest suite |
| `docs/` | Architecture, methodology and validation docs |

## Setup (Windows, Git Bash)
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # or requirements.lock.txt for exact versions
.venv/Scripts/python -m pytest -q
```
See `PROGRESS.md` for per-stage run instructions and `DECISIONS.md` for design choices.
