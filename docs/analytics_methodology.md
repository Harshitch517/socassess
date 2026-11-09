# Analytics methodology

The engine (`backend/socassess/analytics/`) reads the unified store and produces **findings**,
**entity risk scores**, a **review queue**, **peer benchmarks**, **alert pattern clusters** and
**weekly trends**. Every result is tied to an analysis run recorded in `analysis_runs` with the
input fingerprint, the full parameter set and a hash of the analytics code.

Run it with `python scripts/run_analysis.py [--params overrides.json]`. All parameters live in
`analytics/params.py`.

## Finding format
```json
{"entity": "CSE02", "type": "fast_closure", "category": "execution_gap", "severity": "critical",
 "title": "1400 high/critical cases closed within minutes",
 "rationale": "14.9% of closed high/critical cases ... Peer median is 0.0% (robust z = 7.3).",
 "evidence_ids": ["CSE02-CS000123", "..."], "evidence_kind": "case",
 "metric_values": {"rate": 0.149, "count": 1400, "peer_median_rate": 0.0, "z": 7.3, "...": "..."}}
```

## The peer rule (used by every rate-based detector)
An entity is flagged only when **both** hold:
1. the rate passes an **absolute floor** (for example, at least 5% of high/critical cases closed within minutes), and
2. its **robust z-score** against peers from the same data source is at least `z_min = 3`:
   `z = (x − median) / max(1.4826 · MAD, min_scale)`.

The median and MAD are robust: a few bad entities cannot drag the baseline towards themselves.
`min_scale` stops tiny differences between near-identical healthy entities from producing huge z values.
Entities with fewer than `min_cases` relevant cases are not judged on rates.

## Execution-gap detectors
| Type | Logic | Evidence |
|---|---|---|
| `fast_closure` | Closed high/critical cases with time-to-close < 10 min (high) or < 15 min (critical); peer rule on the rate. | Those cases, fastest first |
| `critical_no_escalation` | Closed critical cases with disposition `true_positive` and `escalated = false`; peer rule. | Those cases |
| `template_notes` | Notes are normalised (lower case, punctuation removed) and exact duplicates merged. Distinct texts are compared by TF-IDF (1–2-grams) cosine; pairs ≥ 0.92 are linked and connected components form groups. A case is "templated" if its group has ≥ 5 notes. Peer rule on the share; the rationale names the template and the analysts using it. | Templated cases |
| `repeated_no_remediation` | For each asset + rule, the alert history is split at every remediation. A stretch of ≥ 12 alerts over ≥ 7 days with no fix in between means the root cause was left in place (even if it was fixed later). | Cases in those stretches |
| `sla_gaming` | Share of cases closed in the final 5% of the SLA window, and the bunching ratio against the 10% window before it. Real work thins out towards a deadline; a spike just inside it suggests closing to the metric. Peer rule + ratio ≥ 3. | Cases closed in the final window |
| `sla_breach` | Slow-tail time-to-close outliers: share closed after the deadline; peer rule. | Breaching cases |

## Negative-space detectors
| Type | Logic | Evidence |
|---|---|---|
| `silent_critical_assets` | Critical asset with no telemetry rows, ≥ 50% zero-event days, or a recent (30-day) median below 1% of the typical value for its asset type. | Asset ids |
| `missing_categories` | A category is *expected* if ≥ 75% of same-source peers report it (≥ 3 alerts), checked against all peers and against sector-family peers (power/transport/water form the ICS family). Flagged when the entity has zero alerts in an expected category. | – (category list in metrics) |
| `missing_records` | High/critical alerts with no case at all (≥ 1%), and cases flagged `escalated` with no escalation record (≥ 5%). Only for entities that submit case data. | Alert and case ids |
| `low_activity` | Alerts per asset per day versus same-source peers, on a log scale (robust z ≤ −3 and ≤ 35% of the peer median). The rationale checks telemetry: normal log volume with few alerts points at detection, not collection. | – |

## Anomalies and peer benchmarking
`benchmark.entity_metrics` computes 16 operating metrics per entity: alert rate, high/critical share,
median time-to-close relative to SLA, fast-close share, breach rate, deadline bunching, escalation
rate of critical true positives, false-positive rate, open-case share, uncased-alert share,
note uniqueness and length, remediation rate, category coverage, silent critical-asset share and
cases per analyst per day.

- **Benchmarking:** for each metric the entity's value, the median of all same-source peers and of
  same-size peers, a percentile and a robust z.
- **Anomaly:** an IsolationForest (300 trees, seeded) per data source on robust-scaled metrics.
  An `operational_anomaly` finding is raised only when the forest isolates the entity *and* at
  least one metric has |z| ≥ 3.5. The finding lists those metrics as its drivers, so the black-box
  score is always backed by a readable reason. Its risk weight is low (5) because it overlaps the
  specific detectors.

## Alert pattern clustering
The unit is one *pattern*: all alerts of one rule at one entity. Each pattern has behaviour features
(log volume, share of assets hit, share of days active, burstiness = max/mean daily count,
after-hours share, mean severity) and text features (TF-IDF of rule name + category → truncated SVD).
Both blocks are given equal weight. HDBSCAN (`min_cluster_size = 5`) groups similar patterns across
all entities. Each cluster gets a plain-language label (for example "network ids: high volume, concentrated on
few assets"), its entities and its top rules. Clusters spanning several entities are recurring
cross-entity patterns; noise points are one-off patterns.

## Risk score
`score = min(100, Σ weight[type] × multiplier[severity])`, with multipliers low 0.25, medium 0.5,
high 0.75 and critical 1.0. Weights reflect supervisory impact: unescalated confirmed critical
incidents 25, silent critical assets 20, missing records 18, fast closures 15, SLA gaming 14,
repeated alerts without remediation 12, template notes / missing categories / low activity 10,
SLA breach 8, operational anomaly 5. Bands: ≥ 50 critical, ≥ 30 high, ≥ 10 medium, else low, then raised to the
entity's worst finding severity, so one serious finding means at least a "high" band. The
stored `breakdown` lists every contributing finding and its points.

## Review queue
For each finding, the five most telling records (cases ranked by severity, critical asset, then
fastest closure; assets; alerts) are queued with priority = finding points + entity score / 10.
Each entity with case data also gets five seeded random high/critical cases not already queued as
a **control sample**, so the supervisor checks the tool as well as the entity.

## Known limits
- Thresholds are set for the synthetic data and documented, not learned. Stage 6 measures them.
- Peer comparison needs enough peers; with fewer than 3 same-source peers, `missing_categories` falls back to
  all peers, and IsolationForest needs at least 8 entities.
- Template-note detection is exact pairwise TF-IDF within each entity (about 6 s for 11k notes) and is
  the slowest step.
