"""Local DuckDB store for the unified schema."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pandas as pd

from socassess.config import DB_PATH
from socassess.schema import TABLES, ddl

META_DDL = [
    """CREATE TABLE IF NOT EXISTS ingest_runs (
      run_id VARCHAR PRIMARY KEY, started_at TIMESTAMPTZ NOT NULL, source_name VARCHAR,
      input_sha256 VARCHAR NOT NULL, entity_ids VARCHAR[], period_start TIMESTAMPTZ,
      period_end TIMESTAMPTZ, row_counts JSON, warnings JSON)""",
]


def connect(path: str | Path | None = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open (and initialise) the store. Use ':memory:' for tests."""
    target = str(path or DB_PATH)
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(target, read_only=read_only)
    con.execute("SET TimeZone = 'UTC'")
    if os.environ.get("SOCASSESS_DUCKDB_MEMORY"):  # e.g. "200MB" on a 512 MB host
        con.execute(f"SET memory_limit = '{os.environ['SOCASSESS_DUCKDB_MEMORY']}'")
        con.execute("SET preserve_insertion_order = false")
    if os.environ.get("SOCASSESS_DUCKDB_THREADS"):
        con.execute(f"SET threads = {int(os.environ['SOCASSESS_DUCKDB_THREADS'])}")
    if not read_only:
        for t in TABLES.values():
            con.execute(ddl(t))
        for stmt in META_DDL:
            con.execute(stmt)
    return con


def upsert(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> int:
    """Insert rows, replacing rows that have the same primary key."""
    if df.empty:
        return 0
    cols = TABLES[table].column_names
    frame = df[cols]  # noqa: F841 - referenced by name in the SQL below
    con.execute(f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) SELECT {', '.join(cols)} FROM frame")
    return len(df)


def prune_uploads(con: duckdb.DuckDBPyConnection, keep: int) -> list[str]:
    """Delete all data of uploaded entities except the `keep` most recently ingested ones.
    Used only on a shared public demo, so visitor uploads cannot accumulate without bound."""
    rows = con.execute("""
        SELECT e.entity_id, max(r.started_at) AS last
        FROM entities e
        LEFT JOIN (SELECT unnest(entity_ids) AS entity_id, started_at FROM ingest_runs) r USING (entity_id)
        WHERE e.source = 'upload' GROUP BY 1 ORDER BY last DESC NULLS LAST""").fetchall()
    drop = [r[0] for r in rows[keep:]]
    if drop:
        for table in ("escalations", "cases", "telemetry", "alerts", "assets", "entities"):
            con.execute(f"DELETE FROM {table} WHERE entity_id IN (SELECT unnest(?))", [drop])
    return drop


def known_entities(con: duckdb.DuckDBPyConnection) -> set[str]:
    return {r[0] for r in con.execute("SELECT entity_id FROM entities").fetchall()}
