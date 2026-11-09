"""Shared types and helpers for the analytics engine."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field

import duckdb
import numpy as np
import pandas as pd

SEV_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class Finding:
    entity_id: str
    type: str
    category: str  # execution_gap | negative_space | anomaly
    severity: str  # low | medium | high | critical
    title: str
    rationale: str
    evidence_ids: list[str]
    evidence_kind: str  # case | alert | asset | none
    metric_values: dict = field(default_factory=dict)
    detector: str = ""

    @property
    def finding_id(self) -> str:
        return hashlib.sha1(f"{self.entity_id}|{self.type}|{self.title}".encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["finding_id"] = self.finding_id
        d["entity"] = self.entity_id
        return d


@dataclass
class Data:
    """Analysis-ready frames loaded from the store."""
    entities: pd.DataFrame
    assets: pd.DataFrame
    alerts: pd.DataFrame
    cases: pd.DataFrame  # joined with alert severity/category/asset + derived ttc
    escalations: pd.DataFrame
    telemetry: pd.DataFrame

    def source_of(self) -> dict[str, str]:
        """Peer group per entity (see assign_peer_groups); named for its original meaning."""
        return dict(zip(self.entities.entity_id, self.entities.peer_group, strict=True))

    def with_cases(self) -> set[str]:
        return set(self.cases.entity_id.unique())


def load_data(con: duckdb.DuckDBPyConnection, entity_ids: list[str] | None = None) -> Data:
    where = ""
    params: list = []
    if entity_ids:
        where = "WHERE entity_id IN (SELECT unnest(?))"
        params = [entity_ids]

    def q(sql: str) -> pd.DataFrame:
        # Timestamps go through VARCHAR -> pandas UTC so results don't depend on the local TZ.
        return con.execute(sql, params).df()

    ent = q(f"SELECT * FROM entities {where}")
    ent["source"] = ent["source"].fillna("upload")
    assets = q(f"SELECT * FROM assets {where}")
    alerts = q(f"SELECT * EXCLUDE (ts), strftime(ts, '%Y-%m-%dT%H:%M:%SZ') AS ts FROM alerts {where}")
    alerts["ts"] = pd.to_datetime(alerts["ts"], utc=True)
    cases = q(f"""
        SELECT c.* EXCLUDE (opened_at, closed_at, sla_deadline),
               strftime(c.opened_at, '%Y-%m-%dT%H:%M:%SZ') AS opened_at,
               strftime(c.closed_at, '%Y-%m-%dT%H:%M:%SZ') AS closed_at,
               strftime(c.sla_deadline, '%Y-%m-%dT%H:%M:%SZ') AS sla_deadline,
               a.severity, a.category, a.asset_id, a.rule_name
        FROM (SELECT * FROM cases {where}) c LEFT JOIN alerts a USING (alert_id)""")
    for col in ("opened_at", "closed_at", "sla_deadline"):
        cases[col] = pd.to_datetime(cases[col], utc=True)
    cases["ttc_min"] = (cases.closed_at - cases.opened_at).dt.total_seconds() / 60
    crit = dict(zip(assets.asset_id, assets.criticality, strict=True))
    cases["asset_criticality"] = cases.asset_id.map(crit)
    esc = q(f"SELECT * FROM escalations {where}")
    tel = q(f"SELECT * FROM telemetry {where}")
    ent["peer_group"] = assign_peer_groups(ent, set(cases.entity_id))
    return Data(ent, assets, alerts, cases, esc, tel)


MIN_PEERS = 3


def assign_peer_groups(ent: pd.DataFrame, with_cases: set[str]) -> pd.Series:
    """Entities are compared with peers from the same data source. A source with fewer than
    MIN_PEERS entities (e.g. one organisation's own upload) has no meaningful peers, so it joins the
    reference population: the largest source that has case-management data."""
    counts = ent.source.value_counts()
    ref_pool = ent[ent.entity_id.isin(with_cases)].source.value_counts()
    reference = (ref_pool.index[0] if len(ref_pool) else counts.index[0]) if len(counts) else None
    return ent.source.map(lambda s: s if counts.get(s, 0) >= MIN_PEERS or reference is None else reference)


def peer_z(values: pd.Series, groups: pd.Series, min_scale: float) -> pd.Series:
    """Robust z-score of each value against the other values in its group."""
    def z(s: pd.Series) -> pd.Series:
        med = s.median()
        mad = float((s - med).abs().median()) * 1.4826
        return (s - med) / max(mad, min_scale)
    return values.groupby(groups).transform(z)


def peer_median(values: pd.Series, groups: pd.Series) -> pd.Series:
    return values.groupby(groups).transform("median")


def grade(value: float, cuts: list[tuple[float, str]], default: str = "medium") -> str:
    """cuts: [(threshold, severity)] in descending threshold order."""
    for thr, sev in cuts:
        if value >= thr:
            return sev
    return default


def fmt_pct(x: float) -> str:
    return f"{100 * x:.1f}%" if np.isfinite(x) else "n/a"


def r(x, nd: int = 4):
    """Round for metric_values (keeps JSON small and stable)."""
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else round(float(x), nd)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x
