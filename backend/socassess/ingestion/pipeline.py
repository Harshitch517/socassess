"""Ingest an upload: load -> validate -> store, with an ingest_runs record."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from socassess import store
from socassess.ingestion.adapt import adapt
from socassess.ingestion.loaders import load_any, load_export
from socassess.ingestion.validate import ValidationError, validate


@dataclass
class IngestResult:
    run_id: str
    source_name: str
    input_sha256: str
    entity_ids: list[str]
    row_counts: dict[str, int]
    warnings: list[str] = field(default_factory=list)


def hash_input(path: str | Path) -> str:
    """SHA-256 over file contents (folders: sorted relative paths + contents)."""
    path = Path(path)
    h = hashlib.sha256()
    files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    for f in files:
        if path.is_dir():
            h.update(f.relative_to(path).as_posix().encode())
        with f.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def ingest_tables(con: duckdb.DuckDBPyConnection, raw: dict[str, pd.DataFrame], *,
                  source_name: str, input_sha256: str, source: str = "upload",
                  extra_warnings: list[str] | None = None) -> IngestResult:
    """Validate raw tables and write them in one transaction. Raises ValidationError."""
    tables, report = validate(raw, known_entities=store.known_entities(con))
    if not report.ok:
        raise ValidationError(report)
    if "entities" in tables:
        tables["entities"]["source"] = tables["entities"]["source"].fillna(source)
    warnings = list(extra_warnings or []) + report.warnings
    counts: dict[str, int] = {}
    con.execute("BEGIN TRANSACTION")
    try:
        for name in ("entities", "assets", "alerts", "cases", "escalations", "telemetry"):
            if name in tables:
                counts[name] = store.upsert(con, name, tables[name])
        ids = sorted({e for df in tables.values() if "entity_id" in df for e in df["entity_id"].dropna()})
        ts = tables["alerts"]["ts"] if "alerts" in tables else pd.Series(dtype="datetime64[ns, UTC]")
        run_id = uuid.uuid4().hex[:12]
        con.execute("INSERT INTO ingest_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
            run_id, datetime.now(UTC), source_name, input_sha256, ids,
            None if ts.empty else ts.min().to_pydatetime(),
            None if ts.empty else ts.max().to_pydatetime(),
            json.dumps(counts), json.dumps(warnings)])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return IngestResult(run_id, source_name, input_sha256, ids, counts, warnings)


def ingest_path(con: duckdb.DuckDBPyConnection, path: str | Path, source: str = "upload",
                entity_name: str | None = None, auto_map: bool = True,
                source_name: str | None = None, sector: str | None = None,
                size: str | None = None) -> IngestResult:
    """Ingest a file or folder. With auto_map, non-schema exports (e.g. a SIEM alert CSV) are mapped
    automatically; every assumption is returned as a warning prefixed 'auto-mapping:'."""
    path = Path(path)
    if not auto_map:
        raw, ignored = load_export(path)
        warn = [f"ignored unrecognised file/table: {n}" for n in ignored]
    else:
        raw, ignored, extra = load_any(path)
        raw, notes = adapt(raw, extra, known_entities=store.known_entities(con),
                           default_entity=entity_name or path.stem, sector=sector, size=size)
        used_extra = any(n.startswith("'") and "treated as the alerts table" in n for n in notes)
        warn = [f"auto-mapping: {n}" for n in notes]
        if not used_extra:
            warn += [f"ignored unrecognised file/table: {n}" for n in ignored]
    return ingest_tables(con, raw, source_name=source_name or path.name, input_sha256=hash_input(path),
                         source=source, extra_warnings=warn)
