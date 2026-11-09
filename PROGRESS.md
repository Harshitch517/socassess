# Progress

## Stage 0 — Setup (2026-11-09) ✅
- Environment: Windows 11, Python 3.11.9, Node 24.19.0 / npm 11.17.0, Git 2.55, Docker 29.9.2 + Compose v5.6.1, RTX 4050 6 GB. 273 GB free on C:.
- Created the repo structure (`backend/ frontend/ data/raw/ data/processed/ scripts/ tests/ docs/`), `.venv`, `requirements.txt` + lock, `.gitignore`, `.gitattributes`, `pyproject.toml`.
- Smoke tests: 4 passed; ruff clean. Key versions: scikit-learn 1.9.1, DuckDB 2.0.0, FastAPI 0.162.2, pandas 3.1.1.
- Run: `.venv/Scripts/python -m pytest -q`
