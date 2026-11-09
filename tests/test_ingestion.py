import json
import sqlite3
import zipfile

import pandas as pd
import pytest

from socassess import store
from socassess.ingestion.ait import load_ait_tables
from socassess.ingestion.loaders import LoadError, load_export
from socassess.ingestion.pipeline import ingest_path
from socassess.ingestion.validate import ValidationError, validate

ENT = [{"entity_id": "E1", "name": "Org One", "sector": "power", "size": "small"}]
ASSETS = [{"asset_id": "A1", "entity_id": "E1", "criticality": "critical"},
          {"asset_id": "A2", "entity_id": "E1", "criticality": "Low"}]
ALERTS = [{"alert_id": "AL1", "entity_id": "E1", "asset_id": "A1", "ts": "2026-06-01T10:00:00Z",
           "category": "malware", "severity": "critical", "case_id": "C1"},
          {"alert_id": "AL2", "entity_id": "E1", "asset_id": "A2", "ts": "2026-06-02 11:00",
           "category": "recon", "severity": "LOW", "case_id": None}]
CASES = [{"case_id": "C1", "entity_id": "E1", "alert_id": "AL1", "opened_at": "2026-06-01T10:05:00Z",
          "closed_at": "2026-06-01T12:00:00Z", "status": "closed", "disposition": "true_positive",
          "escalated": "yes", "notes": "checked"}]
ESC = [{"escalation_id": "ES1", "case_id": "C1", "entity_id": "E1",
        "escalated_at": "2026-06-01T11:00:00Z"}]


def bundle(**over):
    t = {"entities": ENT, "assets": ASSETS, "alerts": ALERTS, "cases": CASES, "escalations": ESC}
    t.update(over)
    return {k: pd.DataFrame(v) for k, v in t.items()}


@pytest.fixture
def con():
    c = store.connect(":memory:")
    yield c
    c.close()


def write_csv_dir(path, tables):
    path.mkdir()
    for k, df in tables.items():
        df.to_csv(path / f"{k}.csv", index=False)
    return path


# ---------- loaders ----------

def test_load_csv_folder_with_aliases(tmp_path):
    t = bundle()
    t["entity"] = t.pop("entities")  # singular file name is accepted
    raw, ignored = load_export(write_csv_dir(tmp_path / "x", t))
    assert set(raw) == {"entities", "assets", "alerts", "cases", "escalations"}
    assert ignored == []


def test_load_json_bundle(tmp_path):
    p = tmp_path / "upload.json"
    p.write_text(json.dumps({"entities": ENT, "alerts": ALERTS}))
    raw, _ = load_export(p)
    assert len(raw["alerts"]) == 2


def test_load_sqlite(tmp_path):
    p = tmp_path / "export.sqlite"
    with sqlite3.connect(p) as c:
        for k, df in bundle().items():
            df.to_sql(k, c, index=False)
    c.close()
    raw, _ = load_export(p)
    assert len(raw["cases"]) == 1


def test_load_zip_and_unsafe_zip(tmp_path):
    folder = write_csv_dir(tmp_path / "x", bundle())
    z = tmp_path / "up.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in folder.iterdir():
            zf.write(f, f"export/{f.name}")
    assert "alerts" in load_export(z)[0]
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../evil.csv", "a,b")
    with pytest.raises(LoadError, match="unsafe path"):
        load_export(bad)


def test_load_errors_are_clear(tmp_path):
    with pytest.raises(LoadError, match="no such file"):
        load_export(tmp_path / "missing")
    (tmp_path / "e").mkdir()
    (tmp_path / "e" / "readme.txt").write_text("hi")
    with pytest.raises(LoadError, match="no recognisable tables"):
        load_export(tmp_path / "e")
    p = tmp_path / "broken.json"
    p.write_text("{not json")
    with pytest.raises(LoadError, match="invalid JSON at line 1"):
        load_export(p)


# ---------- validation ----------

def test_valid_bundle_coerces_types():
    tables, rep = validate(bundle())
    assert rep.ok, rep.errors
    assert tables["cases"]["escalated"].tolist() == [True]
    assert tables["alerts"]["severity"].tolist() == ["critical", "low"]
    assert str(tables["alerts"]["ts"].dt.tz) == "UTC"


@pytest.mark.parametrize("over, msg", [
    ({"alerts": [{k: v for k, v in ALERTS[0].items() if k != "severity"}]}, "missing required column"),
    ({"alerts": [ALERTS[0] | {"severity": "urgent"}]}, "invalid value"),
    ({"alerts": [ALERTS[0], ALERTS[0]]}, "duplicate key"),
    ({"alerts": [ALERTS[0] | {"ts": "yesterday-ish"}]}, "unparseable timestamp"),
    ({"cases": [CASES[0] | {"closed_at": "2026-06-01T09:00:00Z"}]}, "closed_at earlier"),
    ({"cases": [CASES[0] | {"escalated": "maybe"}]}, "not a boolean"),
    ({"cases": [CASES[0] | {"closed_at": None}]}, "status 'closed' but closed_at is empty"),
    ({"alerts": [ALERTS[0] | {"entity_id": "E9"}]}, "unknown entity"),
    ({"escalations": [ESC[0] | {"case_id": "C404"}]}, "unknown case"),
])
def test_validation_errors(over, msg):
    _, rep = validate(bundle(**over))
    assert not rep.ok
    assert any(msg in e for e in rep.errors), rep.errors


def test_error_message_names_rows():
    _, rep = validate(bundle(alerts=[ALERTS[0], ALERTS[1] | {"severity": "urgent"}]))
    assert "rows [2]" in rep.errors[0]


def test_gaps_are_not_errors():
    # alert without a case, escalated case without escalation record: findings, not bad input
    _, rep = validate(bundle(escalations=[]))
    assert rep.ok


def test_missing_optional_tables_warn():
    raw = {k: v for k, v in bundle().items() if k in ("entities", "alerts")}
    _, rep = validate(raw)
    assert rep.ok
    assert any("no 'cases' table" in w for w in rep.warnings)


def test_missing_required_table():
    _, rep = validate({"assets": pd.DataFrame(ASSETS)})
    assert any("missing required table 'entities'" in e for e in rep.errors)


# ---------- pipeline / store ----------

def test_ingest_idempotent_and_multi_period(tmp_path, con):
    p1 = write_csv_dir(tmp_path / "p1", bundle())
    r1 = ingest_path(con, p1)
    assert r1.entity_ids == ["E1"] and r1.row_counts["alerts"] == 2
    ingest_path(con, p1)  # same upload again: rows replaced, not duplicated
    assert con.execute("SELECT count(*) FROM alerts").fetchone()[0] == 2
    # next period for the same entity, without the entities table
    later = [{"alert_id": "AL3", "entity_id": "E1", "asset_id": "A1", "ts": "2026-09-05T00:00:00Z",
              "category": "malware", "severity": "high"}]
    p2 = write_csv_dir(tmp_path / "p2", {"alerts": pd.DataFrame(later)})
    ingest_path(con, p2)
    assert con.execute("SELECT count(*) FROM alerts").fetchone()[0] == 3
    runs = con.execute("SELECT count(*), count(DISTINCT input_sha256) FROM ingest_runs").fetchone()
    assert runs == (3, 2)


def test_failed_ingest_writes_nothing(tmp_path, con):
    p = write_csv_dir(tmp_path / "bad", bundle(alerts=[ALERTS[0] | {"severity": "urgent"}]))
    with pytest.raises(ValidationError, match="invalid value"):
        ingest_path(con, p)
    assert con.execute("SELECT count(*) FROM entities").fetchone()[0] == 0


def test_ait_adapter(tmp_path):
    df = pd.DataFrame({
        "scenario": ["s1", "s1", "s2"], "detector": ["wazuh", "aminer", "wazuh"],
        "ts": pd.to_datetime(["2022-01-01 00:00", "2022-01-01 00:01", "2022-01-02 00:00"]),
        "host": ["web", None, "mail"], "rule_id": ["1", "x", "2"], "rule_level": [10, None, 3],
        "description": ["scan", "AMiner: New event type.", "login"],
        "rule_groups": ["web,web_scan,recon", "audit", "authentication_success"],
        "attack_label": [None, None, None]})
    p = tmp_path / "s.parquet"
    df.to_parquet(p)
    t = load_ait_tables(p)
    tables, rep = validate(t)
    assert rep.ok, rep.errors
    a = tables["alerts"].set_index("rule_name")
    assert a.loc["scan", "severity"] == "high" and a.loc["scan", "category"] == "recon"
    assert a.loc["AMiner: New event type.", "severity"] == "medium"
    assert len(tables["entities"]) == 2


def test_zip_bomb_and_limits_are_rejected(tmp_path):
    from socassess.ingestion.loaders import check_zip

    bomb = tmp_path / "bomb.zip"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("alerts.csv", "0" * (20 * 2**20))  # 20 MB of zeros -> a few KB compressed
    assert bomb.stat().st_size < 100_000
    with pytest.raises(LoadError, match="zip bomb"):
        load_export(bomb)

    many = tmp_path / "many.zip"
    with zipfile.ZipFile(many, "w") as z:
        for i in range(3):
            z.writestr(f"t{i}.csv", "a,b\n1,2\n")
    with zipfile.ZipFile(many) as z:
        with pytest.raises(LoadError, match="3 files; the limit is 2"):
            check_zip(many, z, max_files=2)
        with pytest.raises(LoadError, match="the limit is 0 MB"):
            check_zip(many, z, max_mb=0)

    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"PK\x03\x04 not really a zip")
    with pytest.raises(LoadError, match="not a valid .zip"):
        load_export(broken)
