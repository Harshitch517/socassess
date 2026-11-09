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

## Stage 6 — Validation (2026-11-09) ✅
- `backend/socassess/validation.py` (scoring vs ground truth, review-effort curves) + `scripts/validate.py` (generate → ingest → analyse → evaluate, per seed; charts; report).
- Results (`docs/validation_report.md`), 5 seeds of which 4 held out: **70/70 planted weaknesses detected, 0 wrong findings, 0/20 healthy entities flagged, AUC 1.00, evidence precision 99.0–99.4% and recall 99.8–100%.**
- Tool vs manual sampling: the review queue confirms every weakness after about 54 records (≈4.5 h); random review of the same 54 records confirms 22–33%, and even 3,840 records (≈320 h) plateaus at 64%, because negative-space weaknesses leave no case to sample.
- Tests: 72 passed (3 validation-maths tests).
- Run: `python scripts/validate.py` (about 8 min for 5 seeds; `--seeds 7 --runs 20` for a quick check).

## Stage 7 — Packaging, docs, deployment (2026-11-09) ✅ except the public deploy (waiting for accounts)
- `Dockerfile` (multi-stage, non-root, healthcheck, seeded demo), `docker-compose.yml` (named volume, 4 GB limit), `.dockerignore`, `requirements-runtime.txt`. Image size 1.12 GB.
- **Offline verified:** `docker run --network none`: healthy; UI, API, entity list and PDF served; full analysis re-run inside the container (19 findings, 24 s); outbound internet confirmed unreachable; about 0.4 GB RAM. Compose: results persist across `docker compose restart`.
- Docs: architecture, functional design, data requirements, infrastructure, model details, deployment (+ earlier methodology, schema, API, validation). README rewritten.
- Public demo prepared: `deploy/huggingface/README.md` (Space card), `scripts/prepare_hf_space.py` (tested), `frontend/vercel.json`. **Pending:** the user's Hugging Face and Vercel (and GitHub) accounts.
- Note: the Stage 7 files were first committed together with Stage 6 (0ed58d1); this commit completes them.

## Post-Stage 7: input → results flow, GUIDE data (2026-11-09)
- **Analyze data** page: upload a file (CSV, Excel, JSON, Parquet, SQLite, zip) or paste rows, with an optional organisation name; shows "How your data was read", then pie charts. A CSV template is downloadable.
- **Results** page (all data or the uploaded organisations): tiles, 5 donut charts (concerns by severity, concern areas, entity risk levels, alert severity mix, alert categories), security warnings with rationale, risk ranking. The Overview also shows the pies.
- **Automatic mapping** of any alert export (`backend/socassess/ingestion/adapt.py`); single uploads are compared with the reference population; two false-warning paths closed (category vocabulary, partial metrics).
- **GUIDE** downloaded with the user's Kaggle token and converted (`scripts/convert_guide.py`): 9.5M rows → 100k-alert sample from 12 orgs, ingested via auto-mapping. Store now has 28 organisations and 498k alerts.
- Full analysis is 15 s (was 141 s) with identical results. Synthetic findings are unchanged (19 + 2 real GUIDE findings).
- Verified end to end on a store copy: a 2,000-row Wazuh-style CSV with no organisation column was uploaded, mapped, analysed and charted in 14.5 s.
- Tests: 82 passed.

## Beginner-friendly UI (2026-11-09)
- **New analysis wizard** (home page): 1) describe your data (optional cards for data type, sector, size, organisation name, which checks to show), 2) add data (drag-and-drop upload, paste, or try one of two samples), then a "Here's what we see in your data" panel with offline guesses, reasons and a preview with recognised columns, plus a "Please classify your input for a better result" prompt with *Use these guesses*, 3) the report.
- **Report** (wizard and *My results*): traffic-light overall result, plain-language warnings (headline, why it matters, what to do, details on demand, evidence link), 5 pie charts, PDF and review-queue links.
- Expert pages moved under **Advanced (for analysts)**. Light theme by default, larger text, icons.
- Backend: `POST /api/detect` (offline auto-classification without storing), classification options, `sector`/`size`/`data_type` on `/api/ingest`; the risk band now matches the worst warning; the note-grouping cache makes upload → report about 7 s (was 56 s).
- Verified in real Chrome with Playwright (`scripts/e2e_wizard.py`): sample without classification (prompt shown), pasted data with classification (no prompt), details toggle, results, advanced navigation; 0 console errors. Tests: 86 passed.
