"""Project paths. Everything is local; nothing here reaches the network."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
DB_PATH = DATA_PROCESSED / "socassess.duckdb"
