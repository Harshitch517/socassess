"""Create the two "Try a sample" files offered on the Analyze page.

    python scripts/make_samples.py

frontend/public/samples/
  sample_grid_utility_alerts.csv   plain SIEM-style alert export (foreign column names, text severities,
                                   power-sector host names, no lateral-movement / privilege-escalation alerts)
  sample_bank_full_export.zip      full SOC export (entities, assets, alerts, cases, escalations, telemetry)
                                   with planted fast closures and unescalated critical incidents
Both are synthetic (fictional organisations), generated with fixed seeds.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "public" / "samples"

spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "generate_synthetic.py")
gen = importlib.util.module_from_spec(spec)
sys.modules["gen"] = gen
spec.loader.exec_module(gen)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # 1) alerts-only export in a typical SIEM layout
    grid = gen.Spec("SAMPLE-GRID", "Sample Grid Utility", "power", "small", "North", "csv", ["missing_categories"])
    t, _ = gen.build_entity(grid, np.random.default_rng(101))
    a, assets = t["alerts"], t["assets"].set_index("asset_id")
    a = a[~a.category.isin(["lateral_movement", "privilege_escalation"])]  # the gap the sample demonstrates
    host = a.asset_id.map(assets.hostname).str.replace("sample-grid-", "grid-", regex=False)
    host = host.str.replace("scadahmi", "scada-hmi", regex=False).str.replace("server", "substation-srv", regex=False)
    sev_word = {"low": "Informational", "medium": "Warning", "high": "High", "critical": "Critical"}
    out = a.assign(Timestamp=a.ts.str.replace("T", " ").str.replace("Z", ""), Priority=a.severity.map(sev_word),
                   **{"Alert Name": a.rule_name, "Tactic": a.category.str.replace("_", " ").str.title(),
                      "Device": host, "Sensor": a.source})
    out = out[["Timestamp", "Priority", "Alert Name", "Tactic", "Device", "Sensor"]]
    out.to_csv(OUT / "sample_grid_utility_alerts.csv", index=False)

    # 2) full export from a bank with closure and escalation problems
    bank = gen.Spec("SAMPLE-BANK", "Sample Bank", "banking", "small", "West", "csv",
                    ["fast_closure", "critical_no_escalation"])
    t, _ = gen.build_entity(bank, np.random.default_rng(202))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, df in t.items():
            z.writestr(f"{name}.csv", df.drop(columns=["export_format"], errors="ignore").to_csv(index=False))
    (OUT / "sample_bank_full_export.zip").write_bytes(buf.getvalue())
    for f in sorted(OUT.iterdir()):
        print(f"{f.name:36} {f.stat().st_size / 1024:8.0f} KB")


if __name__ == "__main__":
    main()
