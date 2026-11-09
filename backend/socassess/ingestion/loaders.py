"""Read an upload in CSV, JSON or database-export form into raw DataFrames.

Accepted inputs:
  * a folder of `<table>.csv` / `<table>.json` / `<table>.jsonl` files
  * a SQLite file (.sqlite / .db / .sqlite3) or a DuckDB file (.duckdb)
  * a folder holding one such database file
  * a .zip archive of any of the above
  * a single JSON document {"entities": [...], "alerts": [...], ...}

Table names are mapped through `schema.TABLE_ALIASES`; unknown tables are reported, not loaded.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import duckdb
import pandas as pd

from socassess.schema import TABLE_ALIASES

DB_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".duckdb"}


class LoadError(ValueError):
    """The input could not be read at all."""


def _canonical(name: str) -> str | None:
    return TABLE_ALIASES.get(name.strip().lower())


def _add(out: dict, unknown: list, name: str, df: pd.DataFrame, origin: str) -> None:
    table = _canonical(name)
    if table is None:
        unknown.append(origin)
        return
    if table in out:
        out[table] = pd.concat([out[table], df], ignore_index=True)
    else:
        out[table] = df


def _read_db(path: Path, out: dict, unknown: list) -> None:
    if path.suffix.lower() == ".duckdb":
        con = duckdb.connect(str(path), read_only=True)
        try:
            for (name,) in con.execute("SELECT table_name FROM information_schema.tables").fetchall():
                _add(out, unknown, name, con.execute(f'SELECT * FROM "{name}"').df(), f"{path.name}:{name}")
        finally:
            con.close()
        return
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    except sqlite3.DatabaseError as e:
        raise LoadError(f"{path.name}: not a readable SQLite database ({e})") from e
    try:
        for name in names:
            _add(out, unknown, name, pd.read_sql_query(f'SELECT * FROM "{name}"', con),
                 f"{path.name}:{name}")
    finally:
        con.close()


def _read_json(path: Path, out: dict, unknown: list) -> None:
    if path.suffix.lower() == ".jsonl":
        _add(out, unknown, path.stem, pd.read_json(path, lines=True, dtype=False), path.name)
        return
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise LoadError(f"{path.name}: invalid JSON at line {e.lineno} column {e.colno}: {e.msg}") from e
    if isinstance(doc, list):
        _add(out, unknown, path.stem, pd.DataFrame.from_records(doc), path.name)
    elif isinstance(doc, dict) and all(isinstance(v, list) for v in doc.values()):
        for name, rows in doc.items():  # bundle document
            _add(out, unknown, name, pd.DataFrame.from_records(rows), f"{path.name}:{name}")
    elif isinstance(doc, dict):
        _add(out, unknown, path.stem, pd.DataFrame([doc]), path.name)
    else:
        raise LoadError(f"{path.name}: expected a JSON array of records or an object of arrays")


def _read_file(path: Path, out: dict, unknown: list) -> None:
    suf = path.suffix.lower()
    if suf == ".csv":
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
        except (pd.errors.ParserError, UnicodeDecodeError) as e:
            raise LoadError(f"{path.name}: could not parse CSV ({e})") from e
        _add(out, unknown, path.stem, df, path.name)
    elif suf in (".json", ".jsonl"):
        _read_json(path, out, unknown)
    elif suf in DB_SUFFIXES:
        _read_db(path, out, unknown)
    elif suf == ".parquet":
        _add(out, unknown, path.stem, pd.read_parquet(path), path.name)
    elif not path.name.startswith("."):
        unknown.append(path.name)


def load_export(path: str | Path) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Return ({canonical_table: DataFrame}, [ignored file/table names])."""
    path = Path(path)
    if not path.exists():
        raise LoadError(f"{path}: no such file or folder")
    out: dict[str, pd.DataFrame] = {}
    unknown: list[str] = []
    if path.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.startswith(("/", "\\")) or ".." in Path(name).parts:
                    raise LoadError(f"{path.name}: unsafe path inside archive: {name}")
            z.extractall(tmp)
            files = sorted(p for p in Path(tmp).rglob("*") if p.is_file())
            for f in files:
                _read_file(f, out, unknown)
    elif path.is_dir():
        for f in sorted(p for p in path.iterdir() if p.is_file()):
            _read_file(f, out, unknown)
    else:
        _read_file(path, out, unknown)
    if not out:
        raise LoadError(f"{path.name}: no recognisable tables found "
                        f"(expected files such as entities.csv, alerts.csv; saw {unknown or 'nothing'})")
    return out, unknown
