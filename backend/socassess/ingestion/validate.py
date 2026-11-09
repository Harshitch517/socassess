"""Validate and coerce raw tables into the unified schema.

Errors make the upload unusable (missing required column, bad enum value, duplicate key,
unknown entity, closed before opened...). Warnings are kept with the ingestion record but do not
block it. Gaps such as alerts without cases are deliberately *not* errors: they are things
the analytics engine has to detect, so rejecting them would hide the evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from socassess.schema import COLUMN_ALIASES, TABLES, Table

MAX_EXAMPLES = 5
TRUE = {"true", "1", "yes", "y", "t"}
FALSE = {"false", "0", "no", "n", "f"}


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


class ValidationError(ValueError):
    def __init__(self, report: ValidationReport):
        self.report = report
        lines = "\n  - ".join(report.errors)
        super().__init__(f"{len(report.errors)} validation error(s):\n  - {lines}")


def _rows(mask: pd.Series) -> str:
    """Describe failing rows as 1-based data row numbers (header excluded)."""
    idx = [int(i) + 1 for i in mask[mask].index[:MAX_EXAMPLES]]
    more = int(mask.sum()) - len(idx)
    return f"rows {idx}" + (f" and {more} more" if more > 0 else "")


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c: COLUMN_ALIASES.get(str(c).strip().lower(), str(c).strip().lower()) for c in df.columns}
    return df.rename(columns=cols)


def _blank(s: pd.Series) -> pd.Series:
    return s.isna() | s.astype(str).str.strip().isin(["", "nan", "NaT", "None", "null"])


def _coerce(table: Table, df: pd.DataFrame, rep: ValidationReport) -> pd.DataFrame:
    df = _normalise_columns(df).reset_index(drop=True)
    if df.empty and len(df.columns) == 0:  # e.g. JSON [] : no rows, so nothing to check
        rep.warn(f"{table.name}: table is empty")
        df = pd.DataFrame(columns=table.column_names)
    missing = [c for c, _, req in table.columns if req and c not in df.columns]
    if missing:
        rep.error(f"{table.name}: missing required column(s) {missing}; found {list(df.columns)}")
        return df
    extra = [c for c in df.columns if c not in table.column_names]
    if extra:
        rep.warn(f"{table.name}: ignored unknown column(s) {extra}")
    out = pd.DataFrame(index=df.index)
    for name, kind, req in table.columns:
        raw = df[name] if name in df.columns else pd.Series([None] * len(df), index=df.index)
        blank = _blank(raw)
        if kind == "str":
            col = raw.where(~blank).map(lambda v: None if v is None or pd.isna(v) else str(v).strip())
        elif kind.startswith("enum:"):
            allowed = kind[5:].split("|")
            col = raw.where(~blank).map(lambda v: None if v is None or pd.isna(v)
                                        else str(v).strip().lower())
            bad = col.notna() & ~col.isin(allowed)
            if bad.any():
                vals = sorted(col[bad].unique().tolist())[:MAX_EXAMPLES]
                rep.error(f"{table.name}.{name}: invalid value(s) {vals} in {_rows(bad)}; "
                          f"allowed: {allowed}")
        elif kind == "ts":
            col = pd.to_datetime(raw.where(~blank), utc=True, errors="coerce", format="mixed")
            bad = col.isna() & ~blank
            if bad.any():
                rep.error(f"{table.name}.{name}: unparseable timestamp(s) "
                          f"{raw[bad].astype(str).head(3).tolist()} in {_rows(bad)}")
        elif kind == "date":
            col = pd.to_datetime(raw.where(~blank), errors="coerce", format="mixed").dt.date
            bad = col.isna() & ~blank
            if bad.any():
                rep.error(f"{table.name}.{name}: unparseable date(s) in {_rows(bad)}")
        elif kind == "int":
            col = pd.to_numeric(raw.where(~blank), errors="coerce")
            bad = (col.isna() & ~blank) | (col.notna() & (col % 1 != 0))
            if bad.any():
                rep.error(f"{table.name}.{name}: non-integer value(s) in {_rows(bad)}")
            col = col.astype("Int64")
        elif kind == "bool":
            txt = raw.where(~blank).map(lambda v: None if v is None or pd.isna(v) else str(v).strip().lower())
            col = txt.map(lambda v: True if v in TRUE else False if v in FALSE else None)
            bad = txt.notna() & col.isna()
            if bad.any():
                rep.error(f"{table.name}.{name}: not a boolean in {_rows(bad)} "
                          f"(use true/false, 1/0 or yes/no)")
            col = col.astype("boolean")
        else:  # pragma: no cover - schema bug
            raise AssertionError(kind)
        if req:
            null = col.isna() & blank
            if null.any():
                rep.error(f"{table.name}.{name}: required value missing in {_rows(null)}")
        out[name] = col
    dup = out.duplicated(list(table.primary_key), keep="first")
    if dup.any():
        rep.error(f"{table.name}: duplicate key {list(table.primary_key)} in {_rows(dup)}")
    return out


def _check_relations(t: dict[str, pd.DataFrame], rep: ValidationReport,
                     known_entities: set[str]) -> None:
    entities = set(t["entities"]["entity_id"].dropna()) | known_entities if "entities" in t \
        else known_entities
    for name, df in t.items():
        if name != "entities" and "entity_id" in df:
            bad = df["entity_id"].notna() & ~df["entity_id"].isin(entities)
            if bad.any():
                rep.error(f"{name}.entity_id: unknown entity {sorted(df.loc[bad, 'entity_id'].unique())[:5]} "
                          f"in {_rows(bad)}; add it to the entities table")
    if "assets" in t and "alerts" in t:
        bad = t["alerts"]["asset_id"].notna() & ~t["alerts"]["asset_id"].isin(t["assets"]["asset_id"])
        if bad.any():
            rep.warn(f"alerts.asset_id: {int(bad.sum())} alert(s) reference assets not in the inventory")
    if "cases" in t:
        c = t["cases"]
        if {"opened_at", "closed_at"} <= set(c):
            bad = c["closed_at"].notna() & (c["closed_at"] < c["opened_at"])
            if bad.any():
                rep.error(f"cases: closed_at earlier than opened_at in {_rows(bad)}")
        if {"status", "closed_at"} <= set(c):
            bad = (c["status"] == "closed") & c["closed_at"].isna()
            if bad.any():
                rep.error(f"cases: status 'closed' but closed_at is empty in {_rows(bad)}")
        if "alerts" in t and "alert_id" in c:
            bad = c["alert_id"].notna() & ~c["alert_id"].isin(t["alerts"]["alert_id"])
            if bad.any():
                rep.warn(f"cases.alert_id: {int(bad.sum())} case(s) reference alerts not in this upload")
    if "escalations" in t and "cases" in t and "case_id" in t["escalations"]:
        e = t["escalations"]
        bad = ~e["case_id"].isin(t["cases"]["case_id"])
        if bad.any():
            rep.error(f"escalations.case_id: unknown case(s) in {_rows(bad)}")


def validate(raw: dict[str, pd.DataFrame], known_entities: set[str] | None = None
             ) -> tuple[dict[str, pd.DataFrame], ValidationReport]:
    """Coerce raw tables to the schema. Raises nothing; inspect `report.ok`."""
    rep = ValidationReport()
    known = known_entities or set()
    for name, table in TABLES.items():
        if table.required and name not in raw and not (name == "entities" and known):
            rep.error(f"missing required table '{name}'")
    for name in ("assets", "cases", "escalations", "telemetry"):
        if name not in raw:
            rep.warn(f"no '{name}' table: detectors that need it will be skipped for this upload")
    out = {name: _coerce(TABLES[name], df, rep) for name, df in raw.items() if name in TABLES}
    if rep.ok:
        _check_relations(out, rep, known)
    return out, rep
