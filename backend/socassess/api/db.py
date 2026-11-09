"""Thread-safe access to the DuckDB store for the API.

DuckDB allows one writer per file. The API keeps a single connection and serialises all access
with a lock; requests are short, so this is simpler and safer than connection pools.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from socassess import store
from socassess.analytics.engine import RESULT_DDL

JSON_COLS = {"metric_values", "breakdown", "params", "detector_errors", "categories", "top_rules", "profile",
             "row_counts", "warnings"}


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._con = store.connect(self.path)
        self._con.execute(RESULT_DDL)
        self.lock = threading.RLock()

    @contextmanager
    def connection(self):
        with self.lock:
            yield self._con

    def df(self, sql: str, params: list | None = None) -> pd.DataFrame:
        with self.lock:
            return self._con.execute(sql, params or []).df()

    def rows(self, sql: str, params: list | None = None) -> list[dict]:
        df = self.df(sql, params)
        return to_records(df)

    def one(self, sql: str, params: list | None = None) -> dict | None:
        r = self.rows(sql, params)
        return r[0] if r else None

    def scalar(self, sql: str, params: list | None = None):
        with self.lock:
            row = self._con.execute(sql, params or []).fetchone()
        return row[0] if row else None

    def close(self) -> None:
        with self.lock:
            self._con.close()


def to_records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-safe records (NaN -> null, timestamps -> ISO, JSON columns parsed)."""
    if df.empty:
        return []
    for c in df.columns:
        if isinstance(df[c].dtype, pd.DatetimeTZDtype) or pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].map(lambda v: None if pd.isna(v) else pd.Timestamp(v).isoformat())
    out = json.loads(df.to_json(orient="records", date_format="iso", default_handler=str))
    for rec in out:
        for c in JSON_COLS & rec.keys():
            if isinstance(rec[c], str):
                try:
                    rec[c] = json.loads(rec[c])
                except json.JSONDecodeError:
                    pass
    return out

