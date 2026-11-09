# Architecture

SOCAssess is a single-tenant, offline-first application. Everything (storage, analytics, API and
UI) runs on one machine or in one container, with no external services and no network calls at runtime.

```
 CSE exports (CSV / JSON / SQLite / DuckDB / .zip)         public datasets (AIT, GUIDE)
            │  upload (UI or API)                                   │ scripts/download_data.py
            ▼                                                       ▼
 ┌──────────────────────── ingestion ────────────────────────┐   convert_ait.py → Parquet
 │ loaders.py   read any supported format, map table/column   │   ingestion/ait.py adapter
 │              aliases, safe unzip                           │            │
 │ validate.py  coerce types, enums, keys, references;        │◄───────────┘
 │              row-numbered errors; gaps are NOT errors       │
 │ pipeline.py  one transaction: upsert + ingest_runs record  │
 └───────────────────────────────┬────────────────────────────┘
                                 ▼
                ┌──────── DuckDB file (store.py) ────────┐
                │ entities assets alerts cases           │
                │ escalations telemetry ingest_runs      │
                │ ── results, keyed by run_id ──         │
                │ analysis_runs findings entity_scores   │
                │ entity_benchmarks review_queue         │
                │ pattern_clusters alert_patterns        │
                │ weekly_trends                          │
                └───────┬─────────────────────▲──────────┘
                        ▼                     │ persist(run)
 ┌────────────────────── analytics engine (engine.py) ─────────────────────┐
 │ execution.py      fast closure · critical not escalated · template notes │
 │                   repeat alerts w/o fix · SLA bunching · SLA breach      │
 │ negative_space.py silent critical assets · missing categories ·          │
 │                   missing records · low activity                         │
 │ benchmark.py      16 metrics · peer benchmarks · IsolationForest · trends│
 │ clustering.py     pattern-level HDBSCAN                                   │
 │ scoring.py        transparent risk score · review queue                  │
 └──────────────────────────────────┬───────────────────────────────────────┘
                                    ▼
                FastAPI (api/app.py)  ── /api/* JSON, CSV, PDF (reportlab)
                                    │   same origin
                                    ▼
                React + Vite SPA (frontend/dist) served by the API
```

## Components

| Component | Tech | Responsibility |
|---|---|---|
| Ingestion | pandas, DuckDB, sqlite3 | Read heterogeneous exports, validate against the unified schema, write atomically, record input hash |
| Store | DuckDB (single file) | Columnar storage for raw data and per-run results; SQL for the API |
| Analytics engine | pandas, NumPy, scikit-learn (TF-IDF, HDBSCAN, IsolationForest), SciPy | Detectors, benchmarks, clustering, scoring, review queue |
| API | FastAPI + uvicorn | REST endpoints, uploads, report export, audit log; serves the SPA |
| Frontend | React 19, TypeScript, Tailwind 4, Recharts | Dashboards, drill-down, upload, reports |
| Packaging | Docker (multi-stage), docker-compose | One image with seeded demo data; offline runtime |

## Design choices
- **One process, one file.** DuckDB is embedded, so there is no database server to install or secure.
  The API keeps one connection behind a lock (DuckDB allows a single writer per file).
- **Results are immutable per run.** Every analysis writes new rows tagged with `run_id`, and the API
  reads the latest run by default. Older runs stay queryable for audit and comparison.
- **Gaps are data.** Validation rejects malformed input but deliberately accepts missing cases and
  missing escalation records, because those absences are what the negative-space detectors measure.
- **Explainability by construction.** Detectors are rules over named metrics with peer baselines.
  ML components (IsolationForest, HDBSCAN, TF-IDF) either carry readable drivers or only group items
  for a human to look at; none of them decides a score on its own.

## Code map
```
backend/socassess/
  schema.py  store.py  config.py  validation.py
  ingestion/  loaders.py validate.py pipeline.py ait.py
  analytics/  params.py common.py execution.py negative_space.py benchmark.py clustering.py scoring.py engine.py
  api/        app.py db.py reports.py
frontend/src/ api.ts  components/  pages/
scripts/      download_data.py convert_ait.py generate_synthetic.py ingest.py run_analysis.py validate.py
tests/        unit + API tests (pytest)
```
