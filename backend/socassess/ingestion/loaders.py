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
import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import duckdb
import pandas as pd

from socassess.schema import TABLE_ALIASES

DB_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".duckdb"}
EXTRA = "__extra__"
# Zip-bomb protection: a small archive can expand to many GB. Limits apply to the *declared*
# uncompressed sizes before anything is extracted (overridable via environment variables).
MAX_UNZIPPED_MB = int(os.environ.get("SOCASSESS_MAX_UNZIPPED_MB", "1024"))
MAX_ZIP_FILES = int(os.environ.get("SOCASSESS_MAX_ZIP_FILES", "500"))
MAX_ZIP_RATIO = 200  # an honest CSV compresses ~5-20x; 200x+ is a bomb, not data


class LoadError(ValueError):
    """The input could not be read at all."""


def _canonical(name: str) -> str | None:
    return TABLE_ALIASES.get(name.strip().lower())


def _add(out: dict, unknown: list, name: str, df: pd.DataFrame, origin: str) -> None:
    table = _canonical(name)
    if table is None:
        unknown.append(origin)
        out.setdefault(EXTRA, {})[origin] = df  # kept for automatic mapping (adapt.py)
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
    elif suf in (".xlsx", ".xlsm"):
        try:
            sheets = pd.read_excel(path, sheet_name=None, dtype=str)
        except Exception as e:  # corrupt or password-protected workbook
            raise LoadError(f"{path.name}: could not read Excel workbook ({e})") from e
        for sheet, df in sheets.items():
            name = path.stem if len(sheets) == 1 else sheet
            _add(out, unknown, name, df, f"{path.name}:{sheet}")
    elif suf == ".parquet":
        _add(out, unknown, path.stem, pd.read_parquet(path), path.name)
    elif not path.name.startswith("."):
        unknown.append(path.name)


def load_export(path: str | Path) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Return ({canonical_table: DataFrame}, [ignored file/table names])."""
    tables, unknown, _ = load_any(path)
    if not tables:
        raise LoadError(f"{Path(path).name}: no recognisable tables found "
                        f"(expected files such as entities.csv, alerts.csv; saw {unknown or 'nothing'})")
    return tables, unknown


def check_zip(path: Path, z: zipfile.ZipFile, max_mb: int | None = None, max_files: int | None = None) -> None:
    """Reject unsafe or oversized archives before extracting anything."""
    max_mb = MAX_UNZIPPED_MB if max_mb is None else max_mb
    max_files = MAX_ZIP_FILES if max_files is None else max_files
    infos = [i for i in z.infolist() if not i.is_dir()]
    if len(infos) > max_files:
        raise LoadError(f"{path.name}: archive has {len(infos):,} files; the limit is {max_files:,}")
    for i in infos:
        if i.filename.startswith(("/", "\\")) or ".." in Path(i.filename).parts:
            raise LoadError(f"{path.name}: unsafe path inside archive: {i.filename}")
        if i.compress_size and i.file_size / i.compress_size > MAX_ZIP_RATIO and i.file_size > 10 * 2**20:
            raise LoadError(f"{path.name}: '{i.filename}' expands {i.file_size / i.compress_size:,.0f}x "
                            "when unpacked, which looks like a zip bomb; upload it unzipped instead")
    total = sum(i.file_size for i in infos)
    if total > max_mb * 2**20:
        raise LoadError(f"{path.name}: unpacks to {total / 2**20:,.0f} MB; the limit is {max_mb:,} MB "
                        "(set SOCASSESS_MAX_UNZIPPED_MB to change it)")


def load_any(path: str | Path) -> tuple[dict[str, pd.DataFrame], list[str], dict[str, pd.DataFrame]]:
    """Like load_export, but also returns unrecognised tables ({origin: DataFrame}) instead of failing."""
    path = Path(path)
    if not path.exists():
        raise LoadError(f"{path}: no such file or folder")
    out: dict[str, pd.DataFrame] = {}
    unknown: list[str] = []
    if path.suffix.lower() == ".zip":
        try:
            zf = zipfile.ZipFile(path)
        except zipfile.BadZipFile as e:
            raise LoadError(f"{path.name}: not a valid .zip file ({e})") from e
        with tempfile.TemporaryDirectory() as tmp, zf as z:
            check_zip(path, z)
            z.extractall(tmp)
            files = sorted(p for p in Path(tmp).rglob("*") if p.is_file())
            for f in files:
                _read_file(f, out, unknown)
    elif path.is_dir():
        for f in sorted(p for p in path.iterdir() if p.is_file()):
            _read_file(f, out, unknown)
    else:
        _read_file(path, out, unknown)
    extra = out.pop(EXTRA, {})
    if not out and not extra:
        raise LoadError(f"{path.name}: no recognisable tables found "
                        f"(expected data files such as alerts.csv or entities.csv; saw {unknown or 'nothing'})")
    return out, unknown, extra
