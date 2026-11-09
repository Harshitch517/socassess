# Progress

## Stage 0 — Setup (2026-11-09) ✅
- Environment: Windows 11, Python 3.11.9, Node 24.19.0 / npm 11.17.0, Git 2.55, Docker 29.9.2 + Compose v5.6.1, RTX 4050 6 GB. 273 GB free on C:.
- Created the repo structure (`backend/ frontend/ data/raw/ data/processed/ scripts/ tests/ docs/`), `.venv`, `requirements.txt` + lock, `.gitignore`, `.gitattributes`, `pyproject.toml`.
- Smoke tests: 4 passed; ruff clean. Key versions: scikit-learn 1.9.1, DuckDB 2.0.0, FastAPI 0.162.2, pandas 3.1.1.
- Run: `.venv/Scripts/python -m pytest -q`

## Stage 1 — Data (2026-11-09) ✅ (GUIDE pending Kaggle token)
- `scripts/download_data.py ait|guide`: AIT from Zenodo (MD5 verified, safe unzip); GUIDE via the Kaggle CLI once `~/.kaggle/kaggle.json` exists.
- `scripts/convert_ait.py`: AIT NDJSON → Parquet in `data/processed/ait/` (2.60M Wazuh + 55.6k AMiner alerts; 338k-row 4-scenario sample) in about 5 s.
- `scripts/generate_synthetic.py --seed 7`: 12 CSEs (about 60k alerts/cases) in mixed CSV/JSON/SQLite under `data/raw/synthetic/`; planted weaknesses + evidence ids in `data/processed/ground_truth.json` (committed).
- See `docs/data_sources.md`. Tests: 12 passed. Disk: 3.66 GB total (venv 0.65, AIT raw 2.95), far under the 100 GB budget.
- Run: `python scripts/download_data.py ait && python scripts/convert_ait.py && python scripts/generate_synthetic.py`
