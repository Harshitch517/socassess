"""Convert Microsoft GUIDE (Kaggle) to Parquet and build the working sample.

    python scripts/convert_guide.py [--orgs 12] [--rows 100000]

Outputs (data/processed/guide/):
  guide_train.parquet   all rows of GUIDE_Train.csv (streamed with DuckDB, 4 GB memory cap)
  sample_alerts.parquet ~100k rows from the N organisations with the most alerts, sampled per org
                        (seeded), one row per AlertId, ready for the upload/auto-mapping path

GUIDE has one row per (alert, evidence entity); OrgId is the organisation, Category is the MITRE
tactic, IncidentGrade is the analyst verdict (TruePositive / BenignPositive / FalsePositive). It has
no severity, no case timing and no asset inventory, so on SOCAssess it supports alert-level checks
(category coverage, volume, pattern clustering), not closure or escalation checks.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "guide" / "GUIDE_Train.csv"
OUT = ROOT / "data" / "processed" / "guide"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orgs", type=int, default=12)
    ap.add_argument("--rows", type=int, default=100_000)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET memory_limit = '4GB'; SET preserve_insertion_order = false; SET threads = 4")
    full = OUT / "guide_train.parquet"
    if not full.exists():
        con.execute(f"""COPY (SELECT * FROM read_csv('{SRC.as_posix()}', header = true, sample_size = 200000))
                        TO '{full.as_posix()}' (FORMAT parquet, COMPRESSION zstd)""")
    n_rows, n_alerts, n_orgs = con.execute(
        f"SELECT count(*), count(DISTINCT AlertId), count(DISTINCT OrgId) FROM '{full.as_posix()}'").fetchone()
    print(f"GUIDE train: {n_rows:,} rows, {n_alerts:,} alerts, {n_orgs:,} organisations")
    per_org = args.rows // args.orgs
    sample = OUT / "sample_alerts.parquet"
    con.execute(f"""
        COPY (
          WITH alerts AS (   -- one row per alert: GUIDE repeats the alert once per evidence entity
            SELECT * FROM '{full.as_posix()}' QUALIFY row_number() OVER (PARTITION BY OrgId, AlertId ORDER BY Id) = 1),
          top_orgs AS (SELECT OrgId FROM alerts GROUP BY 1 ORDER BY count(*) DESC LIMIT {args.orgs})
          SELECT Id, 'GUIDE-ORG' || CAST(OrgId AS VARCHAR) AS OrgId, AlertId, Timestamp, DetectorId, AlertTitle,
                 Category, MitreTechniques, IncidentId, IncidentGrade, DeviceId
          FROM alerts JOIN top_orgs USING (OrgId)
          QUALIFY row_number() OVER (PARTITION BY OrgId ORDER BY hash(AlertId, 7)) <= {per_org}
        ) TO '{sample.as_posix()}' (FORMAT parquet, COMPRESSION zstd)""")
    print(con.execute(f"""SELECT count(*) rows, count(DISTINCT OrgId) orgs, count(DISTINCT Category) categories,
                                 min(Timestamp), max(Timestamp) FROM '{sample.as_posix()}'""").fetchone())


if __name__ == "__main__":
    main()
