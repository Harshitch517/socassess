"""Convert the AIT Alert Data Set (NDJSON) to Parquet with DuckDB, streaming file by file.

    python scripts/convert_ait.py

Outputs (data/processed/ait/):
  wazuh_alerts.parquet   all Wazuh alerts, flattened
  aminer_alerts.parquet  all AMiner alerts, flattened
  sample_alerts.parquet  working sample: Wazuh + AMiner alerts from SAMPLE_SCENARIOS

`attack_label` is set when an alert's timestamp falls inside an attack window from labels.csv
for the same scenario. This is a time-window label only (AIT's own labels also use the host),
so treat it as approximate.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "ait" / "extracted"
LABELS = ROOT / "data" / "raw" / "ait" / "labels.csv"
OUT = ROOT / "data" / "processed" / "ait"
SAMPLE_SCENARIOS = ["russellmitchell", "santos", "shaw", "wardbeck"]  # the four smallest

WAZUH_SQL = """
SELECT '{scenario}' AS scenario, 'wazuh' AS detector,
       CAST("@timestamp" AS TIMESTAMP) AS ts,
       predecoder.hostname AS host, agent.ip AS agent_ip,
       rule.id AS rule_id, CAST(rule.level AS INTEGER) AS rule_level,
       rule.description AS description, array_to_string(rule.groups, ',') AS rule_groups,
       location, id AS alert_id
FROM read_ndjson('{path}', columns = {{
    '@timestamp': 'VARCHAR', predecoder: 'STRUCT(hostname VARCHAR)',
    agent: 'STRUCT(ip VARCHAR)',
    rule: 'STRUCT(id VARCHAR, level INTEGER, description VARCHAR, groups VARCHAR[])',
    location: 'VARCHAR', id: 'VARCHAR'}}, ignore_errors = true)
"""

AMINER_SQL = """
SELECT '{scenario}' AS scenario, 'aminer' AS detector,
       to_timestamp(LogData.Timestamps[1])::TIMESTAMP AS ts,
       LogData.LogResources[1] AS log_resource,
       AnalysisComponent.AnalysisComponentType AS component_type,
       AnalysisComponent.AnalysisComponentName AS component_name,
       AnalysisComponent.Message AS message,
       left(LogData.RawLogData[1], 500) AS raw_log
FROM read_ndjson('{path}', columns = {{
    AnalysisComponent: 'STRUCT(AnalysisComponentType VARCHAR, AnalysisComponentName VARCHAR, Message VARCHAR)',
    LogData: 'STRUCT(RawLogData VARCHAR[], Timestamps DOUBLE[], LogResources VARCHAR[])'}},
    ignore_errors = true)
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET memory_limit = '4GB'; SET preserve_insertion_order = false; SET TimeZone = 'UTC'")
    con.execute(f"CREATE TABLE labels AS SELECT * FROM read_csv('{LABELS.as_posix()}')")
    scenarios = sorted({p.name.split("_")[0] for p in SRC.glob("*_wazuh.json")})
    for kind, sql in (("wazuh", WAZUH_SQL), ("aminer", AMINER_SQL)):
        parts = []
        for sc in scenarios:
            path = (SRC / f"{sc}_{kind}.json").as_posix()
            part = OUT / f"_{kind}_{sc}.parquet"
            con.execute(f"""
                COPY (
                  SELECT a.*, (SELECT min_by(l.attack, l.start) FROM labels l
                               WHERE l.scenario = a.scenario AND epoch(a.ts) >= l.start
                                 AND epoch(a.ts) < l."end") AS attack_label
                  FROM ({sql.format(scenario=sc, path=path)}) a
                ) TO '{part.as_posix()}' (FORMAT parquet, COMPRESSION zstd)""")
            n = con.execute(f"SELECT count(*) FROM '{part.as_posix()}'").fetchone()[0]
            print(f"{kind:6} {sc:16} {n:>9,} rows")
            parts.append(part.as_posix())
        dest = OUT / f"{kind}_alerts.parquet"
        con.execute(f"COPY (SELECT * FROM read_parquet({parts})) TO '{dest.as_posix()}' "
                    "(FORMAT parquet, COMPRESSION zstd)")
        for p in parts:
            Path(p).unlink()
    sample = OUT / "sample_alerts.parquet"
    scen = ", ".join(f"'{s}'" for s in SAMPLE_SCENARIOS)
    con.execute(f"""COPY (
        SELECT scenario, detector, ts, host, rule_id, rule_level, description, rule_groups, attack_label
        FROM '{(OUT / 'wazuh_alerts.parquet').as_posix()}' WHERE scenario IN ({scen})
        UNION ALL BY NAME
        SELECT scenario, detector, ts, log_resource AS host, component_type AS rule_id,
               NULL::INTEGER AS rule_level, message AS description, component_name AS rule_groups,
               attack_label
        FROM '{(OUT / 'aminer_alerts.parquet').as_posix()}' WHERE scenario IN ({scen})
    ) TO '{sample.as_posix()}' (FORMAT parquet, COMPRESSION zstd)""")
    print(con.execute(f"""SELECT detector, count(*) n, count(attack_label) labelled
                          FROM '{sample.as_posix()}' GROUP BY 1""").fetchall())


if __name__ == "__main__":
    main()
