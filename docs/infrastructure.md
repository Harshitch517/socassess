# Infrastructure requirements

## Deployment options
| Option | Use | Network |
|---|---|---|
| **Docker (recommended)** `docker compose up -d` | Supervisory workstation or on-premises server | None at runtime (verified with `--network none`) |
| Native Python + Node | Development | None at runtime |
| Public demo (Hugging Face Spaces + Vercel) | Showcase with synthetic data only, read-only | Internet |

## Sizing
Measured on the development laptop (i7-12th gen, 16 GB RAM, Windows 11), demo scale = 16 entities,
398k alerts, 60k cases, 230k telemetry rows:

| Resource | Minimum | Recommended | Measured |
|---|---|---|---|
| CPU | 2 cores x86-64 | 4+ cores | Analysis 17–50 s single process |
| RAM | 2 GB | 4 GB (compose `mem_limit: 4g`) | Peak 0.9 GB during a full analysis |
| Disk | 2 GB | 10 GB + data | Image IMAGE_SIZE; DuckDB store 60 MB for the demo; raw AIT 3 GB (dev only) |
| GPU | none | none | not used |

Scaling guide: analysis cost is roughly linear in cases and alerts, except copy-paste-note detection, which
compares the notes *within one entity* pairwise (about 6 s for 11k notes). For a period of about 50
entities × 20k cases each, expect a few minutes per run and 2–4 GB RAM. Keep a period per run, or raise
`template_notes.similarity` and pre-filter if notes per entity reach 100k+.

## Software
| Item | Version | Licence |
|---|---|---|
| Docker Engine / Desktop | 24+ (tested 29.9) | Apache-2.0 (Engine); Docker Desktop is free for personal, education and small business use |
| Python | 3.11 (image `python:3.11-slim`) | PSF |
| Node (build stage only) | 22 LTS (`node:22-alpine`) | MIT |
| Python packages | `requirements-runtime.txt` (FastAPI, uvicorn, pandas, NumPy, pyarrow, DuckDB, pytz, scikit-learn, SciPy, reportlab, python-multipart, pydantic) | MIT / BSD / Apache-2.0 |
| Frontend packages | `frontend/package.json` (React, React Router, Recharts, Tailwind, Vite, TypeScript) | MIT |

## Offline installation (air-gapped target)
On a machine with internet access:
```bash
docker compose build                      # or: docker build -t socassess:latest .
docker save socassess:latest | gzip > socassess.tar.gz
```
Copy `socassess.tar.gz` and `docker-compose.yml` to the target, then:
```bash
docker load -i socassess.tar.gz
docker compose up -d                      # http://localhost:8000
```
The image already contains the built UI and a seeded demo store. Uploaded data and results go to the
named volume `socassess-data` and survive container restarts and upgrades.

## Security notes
- The container runs as a non-root user (uid 10001). Only port 8000 is exposed. There are no outbound connections.
- Uploads are size-limited (`SOCASSESS_MAX_UPLOAD_MB`), type-checked, unpacked into a temp folder with
  path-traversal checks, and deleted after ingestion.
- There is no built-in authentication (single-user workstation design). For shared deployments, put it behind
  the organisation's reverse proxy with SSO, or set `SOCASSESS_READ_ONLY=1` for view-only instances.
- CORS is restricted to configured origins (`SOCASSESS_CORS_ORIGINS`).

## Configuration
See `api.md` → Settings. Detector parameters: `backend/socassess/analytics/params.py`, or per-run overrides.

## Backup
Back up the volume, which holds the single DuckDB file:
`docker run --rm -v socassess-data:/d -v "$PWD":/b alpine tar czf /b/socassess-backup.tgz -C /d .`
