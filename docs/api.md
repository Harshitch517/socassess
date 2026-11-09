# SOCAssess API

Start: `.venv/Scripts/python -m uvicorn socassess.api.app:app --app-dir backend --port 8000 --no-access-log`
Interactive docs: `http://localhost:8000/docs` (OpenAPI at `/openapi.json`).

Every read endpoint takes an optional `run_id` and defaults to the latest analysis run. Errors return
`{"message": ..., "errors": [...]}` with a matching HTTP status.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Status, version, latest run, read-only flag |
| POST | `/api/ingest?analyse=true` | Upload an export (multipart `files`: one .zip / .sqlite / .duckdb, or several CSV/JSON table files). Validates, stores, and by default re-runs the analysis. 422 with row-level errors on bad input, 413 over the size limit, 415 for wrong file types |
| POST | `/api/analysis/run` | Run the analysis. Body: `{"params": {...overrides}, "entity_ids": [...]}` |
| GET | `/api/params/default` | Default detector parameters |
| GET | `/api/runs`, `/api/runs/{run_id}` | **Audit log** of analysis runs: timestamp, input fingerprint, parameters (+ hash), code version, trigger, detector errors |
| GET | `/api/ingestions` | Audit log of uploads: input SHA-256, row counts, warnings |
| GET | `/api/entities?source=` | Entities with risk score, band, rank, breakdown |
| GET | `/api/entities/{id}` | Entity detail: score breakdown, findings, peer benchmarks, data counts, category mix |
| GET | `/api/findings?entity_id=&type=&severity=&category=&limit=&offset=` | Findings (comma-separated values allowed) |
| GET | `/api/findings/{finding_id}` | Finding + first page of resolved evidence records |
| GET | `/api/findings/{finding_id}/evidence?limit=&offset=` | Evidence drill-down (cases joined with alert/asset/escalation, alerts, or assets with telemetry stats) |
| GET | `/api/records/{case\|alert\|asset}/{id}` | One record with linked alert/case/escalations or telemetry series |
| GET | `/api/summary` | Totals, findings by type and severity, band counts |
| GET | `/api/heatmap` | Entity × finding-type matrix of risk points and worst severity |
| GET | `/api/clusters?entity_id=`, `/api/clusters/{id}` | Alert pattern clusters and their member patterns (`-1` = unclustered) |
| GET | `/api/trends?entity_id=a,b` | Weekly alerts, closures, median time-to-close, fast closures, breaches, escalations |
| GET | `/api/review-queue?entity_id=&include_spot_checks=` | Ranked records to review by hand |
| GET | `/api/reports/{entities\|findings\|review_queue\|benchmarks}.csv` | CSV exports |
| GET | `/api/reports/summary.pdf`, `/api/reports/entity/{id}.pdf` | PDF reports (footer carries run id, input fingerprint and code version) |

## Settings (environment)
| Variable | Default | |
|---|---|---|
| `SOCASSESS_DB` | `data/processed/socassess.duckdb` | Store path |
| `SOCASSESS_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed browser origins |
| `SOCASSESS_MAX_UPLOAD_MB` | `200` | Upload limit |
| `SOCASSESS_READ_ONLY` | `0` | `1` disables upload and analysis (public demo) |
| `SOCASSESS_FRONTEND_DIR` | – | Serve a built frontend from the same origin |

Measured on the full store (16 entities, 398k alerts): JSON endpoints 4–100 ms; PDF reports about 0.2 s.
