"""A small, clean multi-entity world for detector unit tests.

`world()` returns raw tables; tests plant one weakness, then `load(tables)` ingests them into an
in-memory store through the real validation path and returns the analysis `Data`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from socassess import store
from socassess.analytics.common import load_data
from socassess.analytics.params import DEFAULT_PARAMS
from socassess.ingestion.pipeline import ingest_tables

START = pd.Timestamp("2026-06-01", tz="UTC")
DAYS = 60
SLA_H = {"critical": 4, "high": 8, "medium": 24, "low": 72}
CATS = ["malware", "phishing", "brute_force", "recon", "policy_violation", "lateral_movement",
        "privilege_escalation", "data_exfiltration"]
WORDS = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november "
         "oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee zulu").split()


def world(n: int = 8, alerts_per: int = 300, seed: int = 0) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    ents, assets, alerts, cases, escs, tel = [], [], [], [], [], []
    for e in range(n):
        eid = f"E{e}"
        ents.append({"entity_id": eid, "name": f"Entity {e}", "sector": "power" if e < n // 2 else "banking",
                     "size": "medium", "source": "synthetic"})
        for a in range(20):
            assets.append({"asset_id": f"{eid}-A{a:02d}", "entity_id": eid,
                           "asset_type": "domain_controller" if a < 3 else "workstation",
                           "criticality": "critical" if a < 3 else "medium"})
            counts = rng.poisson(1000, DAYS)
            for day in range(DAYS):
                tel.append({"entity_id": eid, "asset_id": f"{eid}-A{a:02d}",
                            "date": (START + pd.Timedelta(days=day)).date(), "event_count": int(counts[day])})
        for i in range(alerts_per):
            aid, cid = f"{eid}-AL{i:05d}", f"{eid}-CS{i:05d}"
            cat = CATS[i % len(CATS)]
            sev = rng.choice(["low", "medium", "high", "critical"], p=[0.3, 0.3, 0.25, 0.15])
            ts = START + pd.Timedelta(seconds=int(rng.integers(0, DAYS * 86400)))
            asset = f"{eid}-A{int(rng.integers(0, 20)):02d}"
            rule = f"{cat} rule {i % 2}"
            alerts.append({"alert_id": aid, "entity_id": eid, "asset_id": asset, "ts": ts, "category": cat,
                           "severity": sev, "rule_name": rule, "case_id": cid})
            opened = ts + pd.Timedelta(minutes=5)
            sla = pd.Timedelta(hours=SLA_H[sev])
            ttc = sla * 0.3 * float(rng.lognormal(0, 0.5))
            tp = rng.random() < 0.25
            esc = tp and (sev == "critical" or (sev == "high" and rng.random() < 0.5))
            note = (f"Investigated {rule} on {asset}. " + " ".join(rng.choice(WORDS, 8)) +
                    f" ref {rng.integers(1e6, 1e7)} events {rng.integers(1, 999)}.")
            cases.append({"case_id": cid, "entity_id": eid, "alert_id": aid, "assignee": f"{eid}.an{i % 4}",
                          "opened_at": opened, "closed_at": opened + ttc, "sla_deadline": opened + sla,
                          "status": "closed", "disposition": "true_positive" if tp else "false_positive",
                          "escalated": esc, "remediation": "host isolated" if tp else None, "notes": note})
            if esc:
                escs.append({"escalation_id": cid.replace("CS", "ES"), "case_id": cid, "entity_id": eid,
                             "escalated_at": opened + ttc / 2, "escalated_to": "CISO"})
    return {"entities": pd.DataFrame(ents), "assets": pd.DataFrame(assets), "alerts": pd.DataFrame(alerts),
            "cases": pd.DataFrame(cases), "escalations": pd.DataFrame(escs), "telemetry": pd.DataFrame(tel)}


def load(tables: dict[str, pd.DataFrame]):
    con = store.connect(":memory:")
    ingest_tables(con, {k: v.copy() for k, v in tables.items()}, source_name="test", input_sha256="0" * 64,
                  source="synthetic")
    return con, load_data(con)


@pytest.fixture
def params():
    import copy
    return copy.deepcopy(DEFAULT_PARAMS)


@pytest.fixture(scope="session")
def clean_tables():
    return world()


@pytest.fixture
def tables(clean_tables):
    return {k: v.copy() for k, v in clean_tables.items()}
