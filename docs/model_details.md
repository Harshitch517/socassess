# Model details

SOCAssess is not a single trained model. It is an **analytics engine**: peer-relative statistical rules
plus three small unsupervised ML components. This document covers each component's design, hardware
needs, how it is trained or updated offline, how it is explained, and how it is audited.

## 1. Components

| Component | Type | Library | Learns from | Output |
|---|---|---|---|---|
| Rate detectors (fast closure, no escalation, SLA bunching, SLA breach, low activity) | Robust statistics: median/MAD z-score vs same-source peers + absolute floor | NumPy/pandas | The current batch of entities (no stored model) | Finding + rate, peer median, z |
| Copy-paste notes | TF-IDF (1–2-grams) + cosine ≥ 0.92 + connected components | scikit-learn, SciPy | Notes within each entity | Template groups, analyst breakdown |
| Repeat alerts, no fix | Rule: run of ≥ 12 alerts over ≥ 7 days per asset+rule without remediation | pandas | – | Asset/rule pairs, case ids |
| Silent critical assets | Rule on telemetry: zero-day share ≥ 50% or recent median < 1% of asset-type median | pandas | Telemetry of all assets of the same type | Asset ids, reasons |
| Missing categories | Peer presence: category seen by ≥ 75% of same-source (and sector-family) peers | pandas | Current peers | Missing categories |
| Missing records | Rule: uncased high/critical alerts, escalated cases without a record | pandas | – | Alert/case ids |
| Operational anomaly | IsolationForest (300 trees, seed 0) on 16 robust-scaled metrics, per source | scikit-learn | Current peers (fit per run) | Anomaly score + metric drivers with |z| ≥ 3.5 |
| Alert pattern clusters | HDBSCAN (min cluster size 5) on behaviour features + TF-IDF→SVD(8) of rule text | scikit-learn | All patterns in the run | Cluster ids + plain-language labels |
| Risk score | Additive: Σ weight[type] × severity multiplier, capped at 100 | – | – | Score + itemised breakdown |

All parameters are in `backend/socassess/analytics/params.py` and can be overridden per run (API `POST
/api/analysis/run` with `{"params": {...}}` or `scripts/run_analysis.py --params file.json`).

## 2. Why this design
- **Peer-relative, not absolute.** What counts as "fast" or "low" differs by sector and tooling, so each entity
  is compared with entities like it (same data source; sector family for categories; size for benchmarks). The
  median/MAD baseline is robust: a few weak peers cannot shift it towards themselves.
- **Two conditions for a flag** (absolute floor *and* z ≥ 3) keep false alarms down on near-identical
  healthy peers. Validation found no false alarms on healthy entities across 5 seeds (`validation_report.md`).
- **ML only where rules can't reach:** text near-duplication (TF-IDF), "unusual overall profile"
  (IsolationForest), and grouping alert patterns (HDBSCAN). None of these set the score alone.
- **No deep learning, no external AI.** TF-IDF catches every planted copy-paste note, so the optional
  `all-MiniLM-L6-v2` embedding model was not needed (the spec says "TF-IDF first").

## 3. Hardware
| Workload | Measured on this project (i7-12th gen laptop, 16 GB) |
|---|---|
| Full analysis, 16 entities / 398k alerts / 60k cases | 20–50 s, CPU only, single process |
| Validation, one seed (generate + ingest + analyse) | about 100 s |
| API responses | 4–100 ms JSON; about 0.2 s PDF |

No GPU is used. See `infrastructure.md` for memory and disk figures.

## 4. Offline training and updating
- **There is no persisted trained model.** Every component is fitted on the data at analysis time
  (IsolationForest, TF-IDF, HDBSCAN, peer medians), so there is no model file to ship or keep in sync.
  "Updating the model" means uploading the next period's data and re-running.
- **Changing behaviour** means changing parameters (for example raising `fast_closure.max_minutes.high`).
  New parameters apply to the next run and are recorded in that run's audit entry.
- **Re-validating after a change:** `python scripts/validate.py` regenerates five synthetic worlds with known
  weaknesses, re-runs everything and rewrites `docs/validation_report.md`. Run it before adopting new
  parameters or detector code.
- **Determinism:** the generator, IsolationForest, HDBSCAN input and the review-queue control sample are
  all seeded, so the same data and parameters give the same results.

## 5. Explainability
Each finding carries:
- `rationale`: a sentence with the numbers (rate, count, peer median, z, worst example);
- `metric_values`: every quantity the detector used (shown in the UI under "Measured values");
- `evidence_ids`: the exact cases, alerts or assets, which can be opened one by one in the UI;
- `points`: its contribution to the entity score, with weight and severity multiplier.

The IsolationForest finding lists the metrics that drive the anomaly (value, peer median, z). Clusters are
labelled in words ("network ids: high volume, concentrated on few assets") with their top rules.

## 6. Auditability
| Record | Where | Content |
|---|---|---|
| Every upload | `ingest_runs` table, `/api/ingestions` | Time, source name, SHA-256 of the input, entities, alert period, row counts, warnings |
| Every analysis | `analysis_runs` table, `/api/runs` | Time, duration, **input fingerprint** (ingest hashes + per-table row hash), full parameters + hash, **code version** (package version + hash of the analytics source), trigger, detector errors |
| Every result | All result tables carry `run_id` | Findings, scores, benchmarks, queue, clusters and trends for any past run |
| Reports | PDF footer | Run id, input fingerprint, code version |

Given the stored data and the run's parameters, a run can be reproduced and checked: same input fingerprint
and same code version give the same findings.

## 7. Known limitations
- The detectors were tuned and validated on synthetic data with clear-cut planted weaknesses, so real data
  will need parameter review in the first periods.
- Peer comparison weakens with few peers; small sectors fall back to all same-source peers.
- A CSE that games *every* metric uniformly would look normal to the peer-relative rules. The control
  spot-check sample in the review queue partly covers this.
