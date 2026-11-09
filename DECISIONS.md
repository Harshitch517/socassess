# Decisions

| # | Date | Stage | Decision | Why |
|---|---|---|---|---|
| 1 | 2026-11-09 | 0 | Started from scratch; the old INT396 alert-clustering work is retired, and its stale git index was cleared (with the user's approval). | User confirmed a fresh start on the new spec. |
| 2 | 2026-11-09 | 0 | Python 3.11.9 (installed) for the venv. | Matches the spec (3.11+); 3.13 is also present, but 3.11 has the widest wheel support. |
| 3 | 2026-11-09 | 0 | Use `sklearn.cluster.HDBSCAN` instead of the `hdbscan` package. | Bundled with scikit-learn ≥1.3, so there's no C build on Windows and one dependency fewer. |
| 4 | 2026-11-09 | 0 | `reportlab` (BSD) for PDF export; `matplotlib` for validation charts. | Free, offline, pure-pip installs. |
| 5 | 2026-11-09 | 0 | `requirements.txt` holds minimum versions; `requirements.lock.txt` (pip freeze) gives exact reproducible versions. | Flexible for development, reproducible for Docker. |
| 6 | 2026-11-09 | 0 | Backend package lives in `backend/socassess/`; pytest/ruff configured in `pyproject.toml`. | Matches the spec's `backend/` folder and keeps imports clean. |
| 7 | 2026-11-09 | 0 | Git default branch `main`. | Matches the remote convention. |
| 8 | 2026-11-09 | 1 | GUIDE is deferred until the user provides the Kaggle token; Stages 2–3 go ahead on the synthetic and AIT data. | The token comes later; the synthetic data is the primary input for the detectors anyway. |
| 9 | 2026-11-09 | 1 | AIT working sample = 4 smallest scenarios (russellmitchell, santos, shaw, wardbeck); the full 8-scenario Parquet is also kept (17 MB). | The spec asks for "a few scenarios"; Parquet is small enough to keep everything. |
| 10 | 2026-11-09 | 1 | AIT `attack_label` comes from time windows only. | `labels.csv` gives scenario + time windows; host-level labelling would need the full AIT label pipeline. Documented as approximate. |
| 11 | 2026-11-09 | 1 | 12 synthetic CSEs, 4 healthy + 8 with 1–3 planted weaknesses (9 weakness types incl. missing case/escalation records). Mixed export formats (CSV/JSON/SQLite) per entity. | Exercises the Stage 2 loaders and mirrors real multi-organisation submissions. |
| 12 | 2026-11-09 | 1 | Added a `telemetry` table (daily event count per asset) to the synthetic data. | Needed to detect critical assets with no/low telemetry; alert absence alone can't separate "quiet" from "blind". |
| 13 | 2026-11-09 | 1 | Ruff rules pinned to E, F, I, B, UP; line length 110. | Newer ruff defaults enabled noisy style rules (C408). |
| 14 | 2026-11-09 | 2 | Added `telemetry` to the unified schema next to entities/assets/alerts/cases/escalations. | Needed for the "no/low telemetry" check. |
| 15 | 2026-11-09 | 2 | Gaps (alerts without cases, escalated without a record) pass validation. | They are what the negative-space detectors must find; rejecting them would destroy the evidence. |
| 16 | 2026-11-09 | 2 | Upsert by primary key + an `ingest_runs` table holding the input SHA-256. | Idempotent re-uploads, multiple periods per entity, traceable inputs. |
| 17 | 2026-11-09 | 2 | AIT scenarios are ingested as entities with `source='ait'` (no cases); severity from Wazuh rule level; asset criticality unknown → 'medium'. | Gives real alerts for pattern clustering; case-based detectors skip entities without cases. |
| 18 | 2026-11-09 | 2 | Added `pytz` (MIT). | DuckDB needs it to return tz-aware timestamps to Python. |
| 19 | 2026-11-09 | 3 | Rate detectors use "absolute floor AND robust z ≥ 3 vs same-source peers". | Explainable; robust to a few bad peers; avoids alarms on tiny absolute differences. |
| 20 | 2026-11-09 | 3 | Template notes: normalise + exact-merge, then exact TF-IDF cosine ≥ 0.92 with connected components (no MiniLM). | TF-IDF matched all 2,188 planted template notes with no false groups; the embedding model isn't needed (spec: "TF-IDF first"). |
| 21 | 2026-11-09 | 3 | "Repeated without root-cause fix" = a stretch of ≥ 12 alerts over ≥ 7 days on one asset+rule with no remediation in between. | "No remediation ever" missed a planted pair that got an unrelated late fix; a long unfixed stretch is the actual execution gap. |
| 22 | 2026-11-09 | 3 | Alert clustering is pattern-level (entity × rule) with behaviour + text features and sklearn HDBSCAN. | Per-alert clustering of 400k alerts would be slow and unreadable; patterns are what a supervisor reasons about. |
| 23 | 2026-11-09 | 3 | IsolationForest findings need a readable driver (a metric with |z| ≥ 3.5) and carry a low risk weight. | Keeps the anomaly signal explainable and stops it double-counting the specific detectors. |
| 24 | 2026-11-09 | 3 | Risk score = capped sum of weight × severity multiplier, with a stored breakdown. | The spec requires a transparent, non-black-box score. |
| 25 | 2026-11-09 | 3 | The review queue adds a seeded random control sample of high/critical cases per entity. | Lets the supervisor check the tool's blind spots, and is the basis for the Stage 6 manual-sampling baseline. |
| 26 | 2026-11-09 | 3 | The analysis input hash = ingest input hashes + per-table row count + XOR of row hashes. | A pure file-hash missed a change in ingestion mapping; the content fingerprint catches any changed value. |
| 27 | 2026-11-09 | 3 | AIT: Wazuh `freshclam` (AV signature update) → `av_update`, not malware. | The `virus` group label on update events was mislabelling routine updates as malware. |
