"""Unified SOCAssess schema.

Each table lists its columns as (name, kind, required). Kinds:
  str, int, bool, ts (UTC timestamp), date, and enum:<a|b|c>.
Required columns must be present and non-null. Optional columns may be missing from an
upload; they are then stored as NULL.
"""

from __future__ import annotations

from dataclasses import dataclass

SEVERITIES = ("low", "medium", "high", "critical")
CRITICALITY = ("low", "medium", "high", "critical")
DISPOSITIONS = ("true_positive", "false_positive", "benign", "duplicate", "undetermined")
CASE_STATUS = ("open", "closed")
SOURCES = ("synthetic", "ait", "guide", "upload")


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[tuple[str, str, bool], ...]
    primary_key: tuple[str, ...]
    required: bool = False  # must the table itself be present in an upload?

    @property
    def column_names(self) -> list[str]:
        return [c[0] for c in self.columns]


def _enum(values: tuple[str, ...]) -> str:
    return "enum:" + "|".join(values)


ENTITIES = Table("entities", (
    ("entity_id", "str", True),
    ("name", "str", True),
    ("sector", "str", True),
    ("size", _enum(("small", "medium", "large")), True),
    ("region", "str", False),
    ("period_start", "ts", False),
    ("period_end", "ts", False),
    ("source", _enum(SOURCES), False),
), ("entity_id",), required=True)

ASSETS = Table("assets", (
    ("asset_id", "str", True),
    ("entity_id", "str", True),
    ("hostname", "str", False),
    ("asset_type", "str", False),
    ("criticality", _enum(CRITICALITY), True),
    ("owner_team", "str", False),
), ("asset_id",))

ALERTS = Table("alerts", (
    ("alert_id", "str", True),
    ("entity_id", "str", True),
    ("asset_id", "str", False),
    ("ts", "ts", True),
    ("category", "str", True),
    ("severity", _enum(SEVERITIES), True),
    ("rule_name", "str", False),
    ("source", "str", False),
    ("case_id", "str", False),
), ("alert_id",), required=True)

CASES = Table("cases", (
    ("case_id", "str", True),
    ("entity_id", "str", True),
    ("alert_id", "str", False),
    ("assignee", "str", False),
    ("opened_at", "ts", True),
    ("closed_at", "ts", False),
    ("sla_deadline", "ts", False),
    ("status", _enum(CASE_STATUS), True),
    ("disposition", _enum(DISPOSITIONS), False),
    ("escalated", "bool", True),
    ("remediation", "str", False),
    ("notes", "str", False),
), ("case_id",))

ESCALATIONS = Table("escalations", (
    ("escalation_id", "str", True),
    ("case_id", "str", True),
    ("entity_id", "str", True),
    ("escalated_at", "ts", True),
    ("escalated_to", "str", False),
    ("reason", "str", False),
), ("escalation_id",))

TELEMETRY = Table("telemetry", (
    ("entity_id", "str", True),
    ("asset_id", "str", True),
    ("date", "date", True),
    ("event_count", "int", True),
), ("asset_id", "date"))

TABLES: dict[str, Table] = {t.name: t for t in
                            (ENTITIES, ASSETS, ALERTS, CASES, ESCALATIONS, TELEMETRY)}

# Accepted alternative table names in uploads (file stem or SQL table name).
TABLE_ALIASES = {
    "entity": "entities", "entities": "entities", "organisation": "entities",
    "organization": "entities", "asset": "assets", "assets": "assets", "inventory": "assets",
    "asset_inventory": "assets", "alert": "alerts", "alerts": "alerts", "case": "cases",
    "cases": "cases", "incidents": "cases", "escalation": "escalations",
    "escalations": "escalations", "telemetry": "telemetry", "log_volume": "telemetry",
}

# Accepted alternative column names (after lower-casing and stripping).
COLUMN_ALIASES = {
    "timestamp": "ts", "time": "ts", "alert_time": "ts", "created_at": "opened_at",
    "resolved_at": "closed_at", "analyst": "assignee", "owner": "assignee",
    "investigation_notes": "notes", "comment": "notes", "is_escalated": "escalated",
    "escalation_flag": "escalated", "host": "hostname", "sla_due": "sla_deadline",
}

DUCKDB_TYPES = {"str": "VARCHAR", "int": "BIGINT", "bool": "BOOLEAN",
                "ts": "TIMESTAMPTZ", "date": "DATE"}


def duckdb_type(kind: str) -> str:
    return "VARCHAR" if kind.startswith("enum:") else DUCKDB_TYPES[kind]


def ddl(table: Table) -> str:
    cols = ",\n  ".join(f"{name} {duckdb_type(kind)}{' NOT NULL' if req else ''}"
                        for name, kind, req in table.columns)
    return (f"CREATE TABLE IF NOT EXISTS {table.name} (\n  {cols},\n"
            f"  PRIMARY KEY ({', '.join(table.primary_key)})\n)")
