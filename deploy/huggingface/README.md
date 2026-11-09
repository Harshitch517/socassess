---
title: SOCAssess API (demo)
emoji: 🛡️
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 8000
pinned: false
short_description: Supervisory SOC analytics demo API (synthetic data only)
---

# SOCAssess demo backend

Read-only demo of the SOCAssess API on **synthetic data only** (12 fictional CSEs, seed 7).
Upload and analysis endpoints are disabled (`SOCASSESS_READ_ONLY=1`).

- API docs: `/docs`
- The bundled UI is served at `/`; the Vercel frontend calls this Space's `/api/*`.

Source and full documentation: see the project repository.
