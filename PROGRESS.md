# Progress

## Stage 0 — Setup (2026-11-09) ✅
- Environment: Windows 11, Python 3.11.9, Node 24.19.0 / npm 11.17.0, Git 2.55, Docker 29.9.2 + Compose v5.6.1, RTX 4050 6 GB. 273 GB free on C:.
- Created the repo structure (`backend/ frontend/ data/raw/ data/processed/ scripts/ tests/ docs/`), `.venv`, `requirements.txt` + lock, `.gitignore`, `.gitattributes`, `pyproject.toml`.
- Smoke tests: 4 passed; ruff clean. Key versions: scikit-learn 1.9.1, DuckDB 2.0.0, FastAPI 0.162.2, pandas 3.1.1.
- Run: `.venv/Scripts/python -m pytest -q`

## Stage 1 — Data (2026-11-09) ✅ (GUIDE pending Kaggle token)
- `scripts/download_data.py ait|guide`: AIT from Zenodo (MD5 verified, safe unzip); GUIDE via the Kaggle CLI once `~/.kaggle/kaggle.json` exists.
- `scripts/convert_ait.py`: AIT NDJSON → Parquet in `data/processed/ait/` (2.60M Wazuh + 55.6k AMiner alerts; 338k-row 4-scenario sample) in about 5 s.
- `scripts/generate_synthetic.py --seed 7`: 12 CSEs (about 60k alerts/cases) in mixed CSV/JSON/SQLite under `data/raw/synthetic/`; planted weaknesses + evidence ids in `data/processed/ground_truth.json` (committed).
- See `docs/data_sources.md`. Tests: 12 passed. Disk: 3.66 GB total (venv 0.65, AIT raw 2.95), far under the 100 GB budget.
- Run: `python scripts/download_data.py ait && python scripts/convert_ait.py && python scripts/generate_synthetic.py`

## Stage 2 — Ingestion & unified schema (2026-11-09) ✅
- `backend/socassess/schema.py`: entities, assets, alerts, cases, escalations, telemetry (+ `ingest_runs`); docs in `docs/data_schema.md`.
- `ingestion/loaders.py` (CSV/JSON/JSONL/Parquet folders, SQLite/DuckDB exports, .zip with path-traversal check, JSON bundles, table/column aliases), `ingestion/validate.py` (type coercion, enums, keys, references, row-numbered errors), `ingestion/pipeline.py` (transactional upsert + ingest_runs record), `ingestion/ait.py` (AIT adapter), `store.py`.
- Store: `data/processed/socassess.duckdb`, holding 16 entities (12 synthetic + 4 AIT), 398k alerts, 59.7k cases, 2.4k escalations, 230k telemetry rows; full ingest takes about 24 s.
- Tests: 34 passed (22 new ingestion tests).
- Run: `python scripts/ingest.py --fresh` (all data) or `python scripts/ingest.py path/to/upload`

## Stage 3 — Analytics engine (2026-11-09) ✅
- `backend/socassess/analytics/`: `execution.py` (fast_closure, critical_no_escalation, template_notes, repeated_no_remediation, sla_gaming, sla_breach), `negative_space.py` (silent_critical_assets, missing_categories, missing_records, low_activity), `benchmark.py` (16 metrics, peer benchmarks, IsolationForest anomalies, weekly trends), `clustering.py` (pattern-level HDBSCAN), `scoring.py` (transparent risk score + review queue), `engine.py` (run + persist + audit record), `params.py`.
- Method: `docs/analytics_methodology.md`.
- On the synthetic data, every planted weakness type is found in the right entity, with no wrong-type findings and no findings on the 4 healthy CSEs or the AIT testbeds. Healthy entities score 0; all weak ones score > 0. 30 pattern clusters. Full run takes 20–50 s (template notes dominates).
- Results tables (per run_id): analysis_runs, findings, entity_scores, entity_benchmarks, review_queue, pattern_clusters, alert_patterns, weekly_trends.
- Tests: 59 passed (15 detector tests on a clean world with planted weaknesses + 10 engine/scoring tests).
- Run: `python scripts/run_analysis.py`

## Stage 4 — Backend API (2026-11-09) ✅
- FastAPI app `backend/socassess/api/app.py` (+ `db.py`, `reports.py`): upload/ingest, analysis run, audit log (`/api/runs`, `/api/ingestions`), entities + risk scores, entity detail with peer benchmarks, filterable findings, evidence drill-down, records, heatmap, summary, clusters, trends, review queue, CSV + PDF reports. Optional read-only mode and same-origin frontend serving.
- Reference: `docs/api.md`. Live smoke test on the full store: all endpoints 200, 4–210 ms.
- Tests: 68 passed (9 API tests incl. zip/multi-file upload, validation errors, read-only mode, PDFs).
- Run: `.venv/Scripts/python -m uvicorn socassess.api.app:app --app-dir backend --port 8000 --no-access-log`

## Stage 5 — Frontend (2026-11-09) ✅
- `frontend/` (React + Vite + TS + Tailwind + Recharts). Pages: Overview (stat tiles, risk ranking with breakdown tooltips, entity × finding-type heatmap, findings by type, top findings), Entity detail (score breakdown, findings with rationale, category mix, peer comparison strips), Findings (filters) and Finding detail ("why flagged", measured values, paginated evidence with a record drawer incl. telemetry chart), Alert clusters, Trends (≤4 entities, chart/table), Review queue (with control spot-checks), Data upload (drag & drop, validation errors, history), Reports & audit (PDF/CSV, run log with parameters).
- Light/dark/system theme; works from laptop widths down to about 600 px (narrower: tables scroll inside cards).
- Checked visually with headless Chrome screenshots (dark, light, narrow). Typecheck + production build clean (228 kB gzip JS).
- Dev: `cd frontend && npm install && npm run dev` (proxies /api to :8000). Prod: `npm run build`, then run the API with `SOCASSESS_FRONTEND_DIR=frontend/dist` and open http://localhost:8000.
- Tests: 70 passed (added a frontend-serving test).
