import pandas as pd
from conftest import world
from fastapi.testclient import TestClient

from socassess.api.app import Settings, create_app
from socassess.ingestion.detect import detect


def test_alert_export_with_sector_words():
    df = pd.DataFrame({"Timestamp": ["2026-06-01"] * 3, "Severity": ["High", "Low", "High"],
                       "Host": ["grid-scada-01", "substation-hmi-2", "plc-07"], "Rule": ["a", "b", "c"]})
    r = detect({}, {"alerts_june.csv": df}, ["alerts_june.csv"]).to_dict()
    assert r["data_type"]["value"] == "alerts" and r["data_type"]["confidence"] == "high"
    assert r["sector"]["value"] == "power" and "scada" in r["sector"]["reasons"][0]
    assert r["size"]["value"] == "small"
    assert r["mapping"]["Timestamp"] == "ts" and len(r["preview"]) == 3


def test_case_records_and_unknown_sector():
    df = pd.DataFrame({"ticket": [1, 2], "opened": ["2026-06-01"] * 2, "closed_at": ["2026-06-02"] * 2,
                       "assignee": ["a", "b"], "disposition": ["fp", "tp"]})
    r = detect({}, {"tickets.csv": df}, ["tickets.csv"]).to_dict()
    assert r["data_type"]["value"] == "cases"
    assert r["sector"]["value"] == "other" and r["sector"]["confidence"] == "low"


def test_full_export_with_sector_column():
    t = world(n=1, alerts_per=10)
    r = detect(t, {}, ["export.zip"]).to_dict()
    assert r["data_type"]["value"] == "full"
    assert r["sector"]["value"] == "banking" and r["sector"]["confidence"] == "high"  # world(n=1): E0 is banking
    assert r["missing_for_full"] == []


def test_detect_endpoint_and_classified_upload(tmp_path):
    s = Settings()
    s.db_path = str(tmp_path / "d.duckdb")
    csv = "Timestamp,Severity,Alert Title,Host\n2026-06-01 10:00,High,ATM malware,atm-branch-01\n"
    with TestClient(create_app(s)) as c:
        det = c.post("/api/detect", files=[("files", ("x.csv", csv, "text/csv"))]).json()
        assert det["sector"]["value"] == "banking"
        assert c.get("/api/entities").status_code == 404  # detect stores nothing
        r = c.post("/api/ingest", params={"entity_name": "Bank A", "size": "large"},
                   files=[("files", ("x.csv", csv, "text/csv"))]).json()
        assert r["classification"]["size"] == {"value": "large", "label": "Large", "source": "user",
                                               "confidence": "user", "reasons": []}
        assert r["classification"]["sector"]["source"] == "auto" and "sector" in r["auto_classified"]
        ent = c.get("/api/entities/BANK-A").json()["entity"]
        assert (ent["sector"], ent["size"]) == ("banking", "large")
        bad = c.post("/api/ingest", params={"sector": "space"}, files=[("files", ("x.csv", csv, "text/csv"))])
        assert bad.status_code == 422
        assert "sectors" in c.get("/api/classification/options").json()
