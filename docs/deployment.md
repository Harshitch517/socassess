# Deployment

## Live public demo
| | |
|---|---|
| App (UI + API, one address) | **https://socassess-api.onrender.com** |
| API docs | https://socassess-api.onrender.com/docs |
| Source | https://github.com/Harshitch517/socassess (public) |
| Host | Render free web service (Docker), region Singapore, settings in `render.yaml` |

Demo limits (measured in a 512 MB container): uploads ≤ 5 MB (~50,000 alerts), only the 5 most recent visitor uploads are
kept, the data resets whenever the service restarts, and the service sleeps after ~15 min idle (the first visit then takes
~1 min to wake). Analysis takes ~1–2 min on the free CPU. A notice asks visitors not to upload confidential data.

Redeploy after pushing to `main`: Render builds public repos by URL, so it does not receive GitHub push events.
Use the dashboard's *Manual Deploy* or the API: `POST https://api.render.com/v1/services/<service-id>/deploys`.

Vercel was not used: the token provided was read-only ("You don't have permission to create the resource"), and the
Render service already serves the UI. To add a Vercel front end later, create a token with deploy rights and run
`VITE_API_BASE=https://socassess-api.onrender.com npm run build` in `frontend/`, deploy `dist/`, then set
`SOCASSESS_CORS_ORIGINS` on Render to the Vercel URL.


## A. Offline (production use)
```bash
docker compose up -d --build        # first time; needs internet for the build only
# open http://localhost:8000
```
For an air-gapped machine, build elsewhere and transfer the image (`docker save` / `docker load`); see
`infrastructure.md`. The runtime needs no network: this was verified by running the container with
`--network none` and exercising the API from inside it (see `PROGRESS.md`, Stage 7).

Useful commands:
```bash
docker compose logs -f
docker compose exec socassess python scripts/run_analysis.py        # re-run analysis by hand
docker compose down          # stop (data stays in the socassess-data volume)
```

## B. Public demo (synthetic data only, read-only)
Two free hosts: the **backend on Hugging Face Spaces** (Docker SDK, free CPU tier) and the **frontend on
Vercel** (Hobby tier). The demo uses only the synthetic CSEs baked into the image; uploads are disabled.

### 1. Backend: Hugging Face Space
1. Create a Space at https://huggingface.co/new-space: SDK **Docker**, hardware **CPU basic (free)**.
2. Prepare the folder and push it:
   ```bash
   python scripts/prepare_hf_space.py ../socassess-space --cors https://<your-vercel-app>.vercel.app
   cd ../socassess-space
   git init -b main && git add -A && git commit -m "SOCAssess demo"
   git remote add origin https://huggingface.co/spaces/<user>/<space>
   git push -u origin main        # authenticate with a Hugging Face access token (write)
   ```
3. Wait for the build (about 5 minutes). Check `https://<user>-<space>.hf.space/api/health`.

### 2. Frontend: Vercel
1. Import the GitHub repository at https://vercel.com/new and set **Root Directory** = `frontend`
   (framework preset: Vite; `frontend/vercel.json` sets the SPA rewrite).
2. Add the environment variable `VITE_API_BASE` = `https://<user>-<space>.hf.space`.
3. Deploy. If the Vercel URL differs from the one given to `--cors`, update the Space variable
   `SOCASSESS_CORS_ORIGINS` (Space settings → Variables) and restart the Space.

Alternative without Vercel: the Space already serves the same UI at its own URL (`/`).

## C. Development
```bash
.venv/Scripts/python -m uvicorn socassess.api.app:app --app-dir backend --port 8000 --reload
cd frontend && npm run dev          # http://localhost:5173, /api proxied to :8000
```
