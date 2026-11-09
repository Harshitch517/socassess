"""Run the analytics engine on the local store and persist the results.

    python scripts/run_analysis.py [--db data/processed/socassess.duckdb] [--params overrides.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from socassess import store  # noqa: E402
from socassess.analytics.engine import persist, run_analysis  # noqa: E402
from socassess.config import DB_PATH  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--params", type=Path, help="JSON file with parameter overrides")
    args = ap.parse_args()
    overrides = json.loads(args.params.read_text()) if args.params else None
    con = store.connect(args.db)
    res = run_analysis(con, overrides)
    persist(con, res, trigger="cli")
    print(f"run {res.run_id}  {res.duration_s}s  code {res.code_version}  input {res.input_hash[:12]}")
    if res.detector_errors:
        print("DETECTOR ERRORS:", res.detector_errors)
    cols = ["rank", "entity_id", "name", "risk_score", "band", "n_findings", "anomaly_score"]
    print(res.scores[cols].to_string(index=False))
    print(f"\n{len(res.findings)} findings, {len(res.queue)} review items, "
          f"{len(res.clusters)} pattern clusters ({int(res.clusters.cross_entity.sum()) if len(res.clusters) else 0} "
          "cross-entity)")
    for f in sorted(res.findings, key=lambda f: f.entity_id):
        print(f"  {f.entity_id:20} {f.severity:8} {f.type:24} {f.title}")
    return 1 if res.detector_errors else 0


if __name__ == "__main__":
    sys.exit(main())
