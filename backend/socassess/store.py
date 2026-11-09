"""Local DuckDB store for the unified schema."""

from __future__ import annotations

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


def known_entities(con: duckdb.DuckDBPyConnection) -> set[str]:
    return {r[0] for r in con.execute("SELECT entity_id FROM entities").fetchall()}
