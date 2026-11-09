# Decisions

| # | Date | Stage | Decision | Why |
|---|---|---|---|---|
| 1 | 2026-11-09 | 0 | Started from scratch; the old INT396 alert-clustering work is retired, and its stale git index was cleared (with the user's approval). | User confirmed a fresh start on the new spec. |
| 2 | 2026-11-09 | 0 | Python 3.11.9 (installed) for the venv. | Matches the spec (3.11+); 3.13 is also present, but 3.11 has the widest wheel support. |
| 3 | 2026-11-09 | 0 | Use `sklearn.cluster.HDBSCAN` instead of the `hdbscan` package. | Bundled with scikit-learn ≥1.3, so there's no C build on Windows and one dependency fewer. |
| 4 | 2026-11-09 | 0 | `reportlab` (BSD) for PDF export; `matplotlib` for validation charts. | Free, offline, pure-pip installs. |
| 5 | 2026-11-09 | 0 | `requirements.txt` holds minimum versions; `requirements.lock.txt` (pip freeze) gives exact reproducible versions. | Flexible for development, reproducible for Docker. |
| 6 | 2026-11-09 | 0 | Backend package lives in `backend/socassess/`; pytest/ruff configured in `pyproject.toml`. | Matches the spec's `backend/` folder and keeps imports clean. |
| 7 | 2026-11-09 | 0 | Git default branch `main`. | Matches the remote convention. |
