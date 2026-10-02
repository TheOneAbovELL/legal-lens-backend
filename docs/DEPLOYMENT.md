# Deployment

## Container

```bash
docker build -t legal-lens-api .                          # add --build-arg PRELOAD_MODELS=true to bake models in
docker run --env-file .env -p 8000:8000 -v ll-data:/app/data -v ll-models:/models/hf legal-lens-api
docker compose up                                          # API with embedded Qdrant on a volume
docker compose --profile qdrant up                         # plus a Qdrant server (set QDRANT_URL=http://qdrant:6333)
```

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
