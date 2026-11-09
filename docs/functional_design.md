# Functional design

## Users and goal
The primary user is a **supervisory analyst** (for example at NCIIPC) who oversees the security operations of many
critical-sector entities (CSEs). They cannot review every alert and case from every SOC. They need to know
**which entities to look at, what is wrong there, and which records prove it**.

## Core workflow
1. **Collect.** Each CSE submits a periodic export (alerts, cases, escalations, asset inventory, log-volume
   telemetry). The supervisor uploads it on the *Data upload* page; it is validated and stored.
2. **Analyse.** The engine runs automatically after an upload (or on demand) and records an audit entry.
3. **Prioritise.** The *Overview* ranks entities by a transparent risk score. The heatmap shows which
   kind of weakness drives each score.
4. **Understand.** *Entity detail* lists the findings, each with a plain-language rationale, plus a peer
   comparison on 16 operating metrics.
5. **Verify.** *Finding detail* shows the measured values and a paginated evidence table. Any record opens
   in a drawer (case with its alert and escalations; asset with its telemetry chart).
6. **Review by hand.** The *Review queue* lists the specific records to check, strongest evidence first,
   plus a random control sample per entity.
7. **Report.** A summary PDF (all entities) and per-entity PDFs, plus CSV exports, for follow-up with the CSE.

## What it detects
| Group | Finding | Question answered |
|---|---|---|
| Execution gaps | Fast closure | Are serious alerts closed too fast to have been investigated? |
| | Critical not escalated | Are confirmed critical incidents handled without escalation? |
| | Copy-paste notes | Are investigation notes templated rather than written? |
| | Repeat alerts, no fix | Does the same alert keep firing on the same asset with no remediation? |
| | SLA deadline bunching | Are cases closed just inside the SLA to meet the metric? |
| | SLA breaches | Is the slow tail of closures unusually large? |
| Negative space | Silent critical assets | Which critical assets send no telemetry (blind spots)? |
| | Missing alert categories | Which attack categories that peers see does this entity never report? |
| | Missing records | Are serious alerts left without a case, or escalations unrecorded? |
| | Low activity | Is alert volume far below comparable peers? |
| Anomaly | Operational anomaly | Is the overall operating profile unusual (IsolationForest), and why? |

Plus **alert pattern clusters** (recurring patterns within and across entities) and **weekly trends**.

## Pages
| Page | Content |
|---|---|
| Overview | Stat tiles, risk ranking (hover for breakdown), entity × finding-type heatmap, findings by type, top findings |
| Entity detail | Score and band, findings with rationale, score breakdown, category mix, peer comparison strips, entity PDF |
| Findings | Filterable list (entity, type, severity, category) |
| Finding detail | "Why flagged", measured values, detail tables, paginated evidence, record drawer |
| Alert clusters | Cluster list with plain-language labels, cross-entity filter, member patterns |
| Trends | Weekly metric for up to 4 entities, chart or table view |
| Review queue | Ranked records with reason, record drawer, per-browser "done" ticks, CSV export |
| Data upload | Drag-and-drop upload, row-level validation errors, re-run analysis, upload history with hashes |
| Reports & audit | PDF/CSV downloads, analysis run log with parameters, input fingerprint and code version |

## Non-functional requirements
- **Offline.** No external calls at runtime; the Docker image is verified with networking disabled.
- **Free.** Only open-source components (MIT, BSD or Apache-2.0); no paid or external AI APIs.
- **Explainable.** Every finding carries its rationale, metrics and evidence ids; the score is additive.
- **Auditable.** Every upload and analysis run is logged with hashes, parameters and code version.
- **Modest hardware.** Peak memory stays well under 2 GB on the demo data; see `infrastructure.md`.
- **Accessible UI.** Light and dark themes; severity always shown with an icon and text; keyboard-reachable tooltips; table views.
