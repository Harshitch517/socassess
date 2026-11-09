import pandas as pd
from conftest import world

from socassess import store
from socassess.ingestion.adapt import adapt, normalise_severity
from socassess.ingestion.pipeline import ingest_path
from socassess.ingestion.validate import validate


def test_siem_csv_without_entity(tmp_path):
    p = tmp_path / "siem_export.csv"
    pd.DataFrame({
        "Timestamp": ["2026-06-01 10:00", "2026-06-01 11:00", "2026-06-02 09:30"],
        "Severity": ["Informational", "High", "Critical"],
        "Alert Title": ["Port scan", "Malware found", "Ransomware"],
        "Host": ["web01", "pc22", "pc22"],
        "Tactic": ["Reconnaissance", "Execution", "Impact"],
    }).to_csv(p, index=False)
    con = store.connect(":memory:")
    r = ingest_path(con, p, entity_name="Acme Water")
    assert r.entity_ids == ["ACME-WATER"]
    assert any("mapped columns" in w for w in r.warnings)
    rows = con.execute("SELECT severity, category, rule_name, asset_id FROM alerts ORDER BY ts").fetchall()
    assert rows[0] == ("low", "recon", "Port scan", "ACME-WATER:web01")  # Reconnaissance -> peer vocabulary
    assert rows[2][0] == "critical"
    assert con.execute("SELECT name, sector, size FROM entities").fetchone() == ("Acme Water", "unknown", "small")


def test_guide_like_export():
    raw = {}
    extra = {"GUIDE_Train.csv": pd.DataFrame({
        "Id": [1, 2, 3], "OrgId": [7, 7, 9], "AlertId": [100, 100, 101],
        "Timestamp": ["2024-06-04T06:05:15.000Z"] * 3, "Category": ["InitialAccess", "InitialAccess", "Exfiltration"],
        "AlertTitle": [12, 12, 55], "DeviceId": [5, 5, 6], "IncidentGrade": ["TruePositive"] * 3})}
    tables, notes = adapt(raw, extra, known_entities=set(), default_entity="guide")
    a = tables["alerts"]
    assert len(a) == 2  # AlertId 100 appeared twice (one row per evidence entity)
    assert set(a.entity_id) == {"7", "9"} and (a.severity == "medium").all()
    assert set(tables["entities"].entity_id) == {"7", "9"}
    out, rep = validate(tables)
    assert rep.ok, rep.errors
    assert any("treated as the alerts table" in n for n in notes)


def test_numeric_severity_scales():
    notes = []
    s = normalise_severity(pd.Series([0, 3, 5, 9, 13]), notes)
    assert s.tolist() == ["low", "low", "medium", "high", "critical"]
    assert "0-15" in notes[0]
    assert normalise_severity(pd.Series([1, 2, 3, 4]), []).tolist() == ["low", "medium", "high", "critical"]


def test_schema_upload_passes_unchanged(tmp_path):
    t = world(n=2, alerts_per=20)
    tables, notes = adapt({k: v.copy() for k, v in t.items()}, {}, known_entities=set(), default_entity="x")
    assert notes == []
    pd.testing.assert_series_equal(tables["alerts"].asset_id.astype(str), t["alerts"].asset_id.astype(str),
                                   check_names=False)


def test_schema_upload_still_rejects_bad_severity():
    t = world(n=2, alerts_per=10)
    t["alerts"].loc[0, "severity"] = "urgent"
    tables, _ = adapt(t, {}, known_entities=set(), default_entity="x")
    _, rep = validate(tables)
    assert any("invalid value" in e for e in rep.errors)


def test_category_synonyms_and_mitre_names():
    a = pd.DataFrame({"Timestamp": ["2026-06-01"] * 4,
                      "Category": ["CredentialAccess", "Exfiltration", "Policy", "Impact"]})
    tables, notes = adapt({}, {"x.csv": a}, known_entities=set(), default_entity="x")
    assert tables["alerts"].category.tolist() == ["brute_force", "data_exfiltration", "policy_violation", "impact"]
    assert any("renamed" in n for n in notes)


def test_excel_upload(tmp_path):
    p = tmp_path / "soc_report.xlsx"
    pd.DataFrame({"Date": ["2026-06-01 08:00", "2026-06-01 09:00"], "Priority": ["P1", "P3"],
                  "Alert Name": ["Ransomware", "Port scan"]}).to_excel(p, index=False)
    con = store.connect(":memory:")
    r = ingest_path(con, p, entity_name="Excel Org", source_name="soc_report.xlsx")
    assert r.entity_ids == ["EXCEL-ORG"] and r.source_name == "soc_report.xlsx"
    assert con.execute("SELECT severity FROM alerts ORDER BY ts").fetchall() == [("critical",), ("medium",)]
