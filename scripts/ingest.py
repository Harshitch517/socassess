"""Ingest data into the local DuckDB store.

    python scripts/ingest.py                    # all synthetic CSEs + AIT sample
    python scripts/ingest.py path/to/export ... # specific uploads (folder, .zip, .sqlite, .json)
    python scripts/ingest.py --fresh            # delete the DB first
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from socassess import store  # noqa: E402
from socassess.config import DB_PATH  # noqa: E402
from socassess.ingestion.ait import load_ait_tables  # noqa: E402
from socassess.ingestion.pipeline import hash_input, ingest_path, ingest_tables  # noqa: E402
from socassess.ingestion.validate import ValidationError  # noqa: E402

AIT_SAMPLE = ROOT / "data" / "processed" / "ait" / "sample_alerts.parquet"
GUIDE_SAMPLE = ROOT / "data" / "processed" / "guide" / "sample_alerts.parquet"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--no-ait", action="store_true")
    ap.add_argument("--no-guide", action="store_true")
    args = ap.parse_args()
    if args.fresh and args.db.exists():
        args.db.unlink()
    con = store.connect(args.db)
    paths = args.paths or sorted((ROOT / "data" / "raw" / "synthetic").glob("CSE*"))
    failed = 0
    for p in paths:
        try:
            r = ingest_path(con, p, source="synthetic" if not args.paths else "upload")
            print(f"ok   {p.name:10} run={r.run_id} {r.row_counts} warnings={len(r.warnings)}")
        except (ValidationError, ValueError) as e:
            failed += 1
            print(f"FAIL {p.name}: {e}")
    if not args.paths and not args.no_ait and AIT_SAMPLE.exists():
        r = ingest_tables(con, load_ait_tables(AIT_SAMPLE), source_name=AIT_SAMPLE.name,
                          input_sha256=hash_input(AIT_SAMPLE), source="ait")
        print(f"ok   AIT sample run={r.run_id} {r.row_counts}")
    if not args.paths and not args.no_guide and GUIDE_SAMPLE.exists():
        # through the same automatic mapping a user's own alert export goes through
        r = ingest_path(con, GUIDE_SAMPLE, source="guide", entity_name="GUIDE")
        print(f"ok   GUIDE sample run={r.run_id} {r.row_counts}")
    for t in ("entities", "assets", "alerts", "cases", "escalations", "telemetry", "ingest_runs"):
        print(f"{t:12} {con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:>9,}")
    con.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
