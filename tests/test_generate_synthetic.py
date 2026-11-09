import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "generate_synthetic.py")
gen = importlib.util.module_from_spec(spec)
sys.modules["gen"] = gen  # dataclasses need the module registered
spec.loader.exec_module(gen)

BY_ID = {s.entity_id: s for s in gen.SPECS}


@pytest.fixture(scope="module")
def cse11():
    return gen.build_entity(BY_ID["CSE11"], np.random.default_rng(1))


@pytest.fixture(scope="module")
def cse12():
    return gen.build_entity(BY_ID["CSE12"], np.random.default_rng(1))


def test_deterministic():
    a, _ = gen.build_entity(BY_ID["CSE12"], np.random.default_rng(3))
    b, _ = gen.build_entity(BY_ID["CSE12"], np.random.default_rng(3))
    pd.testing.assert_frame_equal(a["cases"], b["cases"])


def test_spec_mix():
    assert 10 <= len(gen.SPECS) <= 15
    assert sum(not s.weaknesses for s in gen.SPECS) >= 3
    planted = {w for s in gen.SPECS for w in s.weaknesses}
    assert planted == {"fast_closure", "critical_no_escalation", "template_notes",
                       "repeated_no_remediation", "silent_critical_assets",
                       "missing_categories", "low_activity", "sla_gaming", "missing_records"}


def test_evidence_ids_exist(cse11):
    tables, gt = cse11
    case_ids = set(tables["cases"].case_id)
    for w in gt["weaknesses"]:
        assert w["evidence_ids"], w["type"]
        assert set(w["evidence_ids"]) <= case_ids


def test_fast_closures_are_fast(cse11):
    tables, gt = cse11
    c = tables["cases"].set_index("case_id")
    ids = next(w["evidence_ids"] for w in gt["weaknesses"] if w["type"] == "fast_closure")
    ttc = pd.to_datetime(c.loc[ids, "closed_at"]) - pd.to_datetime(c.loc[ids, "opened_at"])
    assert (ttc < pd.Timedelta(minutes=5)).all()
    assert c.loc[ids, "severity" if "severity" in c else "disposition"].notna().all()


def test_sla_gaming_closes_just_before_deadline(cse11):
    tables, gt = cse11
    c = tables["cases"].set_index("case_id")
    ids = next(w["evidence_ids"] for w in gt["weaknesses"] if w["type"] == "sla_gaming")
    slack = pd.to_datetime(c.loc[ids, "sla_deadline"]) - pd.to_datetime(c.loc[ids, "closed_at"])
    assert (slack > pd.Timedelta(0)).all()
    assert (slack < pd.Timedelta(hours=1)).all()


def test_silent_assets_have_no_alerts(cse12):
    tables, gt = cse12
    silent = next(w["evidence_ids"] for w in gt["weaknesses"]
                  if w["type"] == "silent_critical_assets")
    assert not tables["alerts"].asset_id.isin(silent).any()
    crit = set(tables["assets"].query("criticality == 'critical'").asset_id)
    assert set(silent) <= crit


def test_missing_categories_absent(cse12):
    tables, gt = cse12
    missing = next(w["categories"] for w in gt["weaknesses"] if w["type"] == "missing_categories")
    assert not tables["alerts"].category.isin(missing).any()


def test_export_formats_roundtrip(tmp_path, cse12):
    tables, _ = cse12
    for fmt in ("csv", "json", "sqlite"):
        gen.write_export(tables, tmp_path / fmt, fmt)
        assert any((tmp_path / fmt).iterdir())
