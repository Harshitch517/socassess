# SOCAssess: one image with the API, the built frontend and seeded demo data.
# Build once with network access; afterwards it runs fully offline (verified with --network none).

# ---- 1. frontend build
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. runtime
FROM python:3.11-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 MALLOC_ARENA_MAX=2 \
    SOCASSESS_DB=/app/data/processed/socassess.duckdb \
    SOCASSESS_FRONTEND_DIR=/app/frontend/dist \
    PORT=8000
WORKDIR /app
COPY requirements-runtime.txt ./
RUN pip install -r requirements-runtime.txt
COPY backend/ backend/
COPY scripts/generate_synthetic.py scripts/ingest.py scripts/run_analysis.py scripts/
COPY --from=web /web/dist frontend/dist
# Seeded demo data: 12 synthetic CSEs, ingested and analysed at build time.
RUN mkdir -p data/raw data/processed \
 && python scripts/generate_synthetic.py --seed 7 \
 && python scripts/ingest.py --fresh --no-ait \
 && python scripts/run_analysis.py \
 && rm -rf data/raw/synthetic \
 && useradd --create-home --uid 10001 socassess \
 && chown -R socassess:socassess /app/data
USER socassess
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health', timeout=4)"
CMD ["sh", "-c", "exec uvicorn socassess.api.app:app --app-dir backend --host 0.0.0.0 --port ${PORT} --no-access-log"]
