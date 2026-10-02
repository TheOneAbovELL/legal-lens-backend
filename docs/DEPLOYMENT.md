# Deployment

```
Browser ── HTTPS reverse proxy ── frontend static files (nginx / CDN)
                              └── FastAPI backend ── Qdrant · PostgreSQL · Groq · (Neo4j)
```

## Containers

```bash
docker build -t legal-lens-api .                          # add --build-arg PRELOAD_MODELS=true to bake models in
docker build -t legal-lens-web ./frontend                 # static build behind nginx, /api proxied to the backend
docker run --env-file .env -p 8000:8000 -v ll-data:/app/data -v ll-models:/models/hf legal-lens-api
docker compose up --build                                  # web :8080 + api :8000 (embedded Qdrant on a volume)
docker compose --profile qdrant up                         # plus a Qdrant server (set QDRANT_URL=http://qdrant:6333)
```

## Frontend hosting options

1. **Separate static hosting (recommended).** `cd frontend && VITE_API_URL=https://api.example.com npm run build`
   and publish `dist/` (nginx, S3+CloudFront, Netlify…). Add the site origin to the backend
   `CORS_ORIGINS`. Streaming works over CORS; keep any proxy's response buffering off for
   `/api/v1/chat/stream` (`frontend/nginx.conf` shows the settings).
2. **Same origin behind nginx.** `frontend/Dockerfile` serves `dist/` and proxies `/api`, `/health`,
   `/ready` to the `api` service, so `VITE_API_URL` stays empty and no CORS is involved.
3. **Served by the backend.** Set `FRONTEND_DIST_PATH=/path/to/frontend/dist`; the API process serves
   the SPA with history fallback (API routes keep precedence). Convenient for single-container
   hosts (Procfile deploys); less efficient than a CDN.

Frontend environment is public-safe only (`VITE_*`). Never place provider keys, the JWT secret or
database URLs in it; CI greps the bundle for secret-looking strings.

The image runs as a non-root user, contains no secrets (`.env` is excluded by `.dockerignore`),
exposes 8000 and has a `/health` HEALTHCHECK. Use `/ready` for load-balancer readiness.

## Production checklist

* `APP_ENV=production` (disables `/docs`; validation requires a ≥ 32-char `JWT_SECRET_KEY` and no
  wildcard CORS).
* `QDRANT_URL` + `QDRANT_API_KEY` (managed Qdrant). Embedded mode supports one process only.
* `DATABASE_URL=postgresql+asyncpg://...` for multi-instance deployments; migrations run at start-up
  (`DB_AUTO_MIGRATE=true`) or explicitly with `alembic upgrade head`.
* `LLM_API_KEY` and a fallback chain in `LLM_PROVIDER_ORDER`.
* `AUTH_REQUIRED=true`, `AUTH_ALLOW_REGISTRATION=false` + `scripts/create_user.py` if signup is closed.
* Memory: each worker loads BGE-M3 (~2.3 GB RAM). Keep `WEB_CONCURRENCY=1` per container and scale
  containers horizontally.
* Rate limits and MEM-0 session memory are per process. Behind several instances, session follow-ups
  need sticky sessions, and strict global rate limits need a shared store (not implemented).
* Logs are JSON on stdout with request IDs; secrets are redacted by pattern.

AWS (per the 2026-01-09 meeting): the image runs unchanged on ECS/Fargate or App Runner with Qdrant
Cloud, RDS PostgreSQL and Groq; use Secrets Manager for `JWT_SECRET_KEY`, `LLM_API_KEY`,
`QDRANT_API_KEY` and `NEO4J_PASSWORD`.

## Migrating from the previous backend

* New collection `legal-lens-chunks` (named dense + sparse vectors, full metadata). The previous
  `legal-lens-qdrant` collection (unnamed vector, `text` payload) can still be read in dense-only mode
  with `QDRANT_COLLECTION=legal-lens-qdrant QDRANT_DENSE_VECTOR_NAME= QDRANT_SPARSE_VECTOR_NAME=
  QDRANT_CREATE_COLLECTION=false`, but re-ingesting is recommended.
* `.env` keys `GROQ_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `NEO4J_*` keep working. Setting
  `NEO4J_URI` enables the graph automatically; set `NEO4J_ENABLED=false` to turn it off.
