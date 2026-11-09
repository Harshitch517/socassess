# Unified data schema

Generated from `backend/socassess/schema.py`. Uploads may be a folder of CSV/JSON files, a SQLite/DuckDB
export, a .zip of either, or one JSON document `{"entities": [...], "alerts": [...]}`.

Kinds: `str`, `int`, `bool` (true/false, 1/0, yes/no), `ts` (any ISO-like timestamp, stored UTC), `date`, `enum` (case-insensitive).

## `entities` (required)
Primary key: `entity_id`

| Column | Kind | Required |
|---|---|---|
| `entity_id` | str | yes |
| `name` | str | yes |
| `sector` | str | yes |
| `size` | enum:small / medium / large | yes |
| `region` | str |  |
| `period_start` | ts |  |
| `period_end` | ts |  |
| `source` | enum:synthetic / ait / guide / upload |  |

## `assets`
Primary key: `asset_id`

| Column | Kind | Required |
|---|---|---|
| `asset_id` | str | yes |
| `entity_id` | str | yes |
| `hostname` | str |  |
| `asset_type` | str |  |
| `criticality` | enum:low / medium / high / critical | yes |
| `owner_team` | str |  |

## `alerts` (required)
Primary key: `alert_id`

| Column | Kind | Required |
|---|---|---|
| `alert_id` | str | yes |
| `entity_id` | str | yes |
| `asset_id` | str |  |
| `ts` | ts | yes |
| `category` | str | yes |
| `severity` | enum:low / medium / high / critical | yes |
| `rule_name` | str |  |
| `source` | str |  |
| `case_id` | str |  |

## `cases`
Primary key: `case_id`

| Column | Kind | Required |
|---|---|---|
| `case_id` | str | yes |
| `entity_id` | str | yes |
| `alert_id` | str |  |
| `assignee` | str |  |
| `opened_at` | ts | yes |
| `closed_at` | ts |  |
| `sla_deadline` | ts |  |
| `status` | enum:open / closed | yes |
| `disposition` | enum:true_positive / false_positive / benign / duplicate / undetermined |  |
| `escalated` | bool | yes |
| `remediation` | str |  |
| `notes` | str |  |

## `escalations`
Primary key: `escalation_id`

| Column | Kind | Required |
|---|---|---|
| `escalation_id` | str | yes |
| `case_id` | str | yes |
| `entity_id` | str | yes |
| `escalated_at` | ts | yes |
| `escalated_to` | str |  |
| `reason` | str |  |

## `telemetry`
Primary key: `asset_id, date`

| Column | Kind | Required |
|---|---|---|
| `entity_id` | str | yes |
| `asset_id` | str | yes |
| `date` | date | yes |
| `event_count` | int | yes |

## Accepted aliases
Table names: `entity`→`entities`, `organisation`→`entities`, `organization`→`entities`, `asset`→`assets`, `inventory`→`assets`, `asset_inventory`→`assets`, `alert`→`alerts`, `case`→`cases`, `incidents`→`cases`, `escalation`→`escalations`, `log_volume`→`telemetry`

Column names: `timestamp`→`ts`, `time`→`ts`, `alert_time`→`ts`, `created_at`→`opened_at`, `resolved_at`→`closed_at`, `analyst`→`assignee`, `owner`→`assignee`, `investigation_notes`→`notes`, `comment`→`notes`, `is_escalated`→`escalated`, `escalation_flag`→`escalated`, `host`→`hostname`, `sla_due`→`sla_deadline`

## Validation rules
- **Errors (upload rejected, nothing written):** missing required table or column, bad enum value, unparseable timestamp/date/bool/int,
  missing required value, duplicate primary key, unknown `entity_id`, `closed_at` before `opened_at`, closed case without `closed_at`,
  escalation pointing at an unknown case. Messages name the table, column and 1-based data rows.
- **Warnings (stored with the run):** unknown columns, missing optional tables, alerts referencing assets not in the inventory,
  cases referencing alerts outside the upload.
- **Not errors on purpose:** alerts without cases and escalated cases without escalation records. They are evidence for the
  negative-space detectors.

## Multiple entities and periods
Rows are upserted by primary key, so re-uploading the same file is idempotent and a later period for the same entity adds rows.
An upload for an entity that is already stored can omit the `entities` table. Every upload writes an `ingest_runs` row
(run id, time, source name, SHA-256 of the input, entity ids, alert period, row counts, warnings).
