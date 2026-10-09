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

## Using the shared data-layer stores

The data-layer workstream loads Supreme Court judgments into its own Qdrant Cloud collection
(`judgment_chunks`: one **unnamed** 1024-d cosine vector, no sparse vectors, ~45 payload fields)
and a Neo4j Aura graph (`Case`/`Statute`/`Judge` nodes; `CITES`, `INTERPRETS`, `REPLACED_BY`,
`HEARD_BY`, `AUTHORED_BY`, `OVERRULES`). The backend reads both without any code change:

1. Set the `QDRANT_*` values exactly as shown in `.env.example` (empty vector names switch the
   store into external-schema mode: the data-layer payload is mapped onto the backend's chunk
   metadata, including `cite_as`, `opinion_type` and `opinion_author`, and internal-only filters
   such as `chunk_profile`/`is_latest` are not sent).
2. Run `python scripts/prepare_external_collection.py` once per collection. Qdrant Cloud rejects
   filters on unindexed payload keys; the script creates the missing keyword/bool indexes
   (additive, touches no data).
3. Set `NEO4J_URI`, `NEO4J_USER` (alias `NEO4J_USERNAME`), `NEO4J_PASSWORD` and `NEO4J_DATABASE`
   from the Aura console. Named provisions then retrieve statute nodes enriched with the cases
   that interpret them, and provision mappings are cross-checked against `REPLACED_BY` edges.
   Use `neo4j+s://`. The `neo4j+ssc://` scheme accepts any certificate and is a local workaround
   for a missing CA bundle; `APP_ENV=production` refuses it.
4. Never ingest into the shared collection: `scripts/ingest.py` refuses external-schema targets,
   and `QDRANT_CREATE_COLLECTION=false` keeps the backend from creating or altering collections
   it does not own.

Aura free instances pause when idle and can refuse routing intermittently after resume; the
circuit breaker turns that into one warning per cooldown window while retrieval continues
without the graph.

### Keeping a keyword leg without sparse vectors

The data-layer collection holds dense vectors only, so the BM25-style `sparse` source returns
nothing there and hybrid retrieval would quietly collapse to dense + exact-provision lookup. The
`lexical` source fills that gap wherever the collection carries a **full-text payload index** over
its body field (`text` or `content`): Qdrant matches the query's distinctive terms and the
retriever ranks the matches by how much of the query each passage covers.

* All terms are required first (precise); if nothing matches, the store sweeps term by term from
  the rarest word down, so one absent term — a typo, a party not in the corpus — cannot sink the
  whole leg.
* Matches covering less than half the query's terms are dropped, keeping single-common-word noise
  out of the fused ranking.
* The source is inert when no full-text index exists, so collections with real sparse vectors are
  unaffected. `GET /ready` and the per-request diagnostics report `lexical` hits alongside
  `dense`, `sparse`, `metadata` and `graph`, so you can see which legs actually ran.

Measured on the live judgment collection, `lexical` contributed 14 passages that dense retrieval
alone did not return across five representative queries.

## Migrating from the previous backend

* New collection `legal-lens-chunks` (named dense + sparse vectors, full metadata). The previous
  `legal-lens-qdrant` collection (unnamed vector, `text` payload) can still be read in dense-only mode
  with `QDRANT_COLLECTION=legal-lens-qdrant QDRANT_DENSE_VECTOR_NAME= QDRANT_SPARSE_VECTOR_NAME=
  QDRANT_CREATE_COLLECTION=false`, but re-ingesting is recommended.
* `.env` keys `GROQ_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `NEO4J_*` keep working. Setting
  `NEO4J_URI` enables the graph automatically; set `NEO4J_ENABLED=false` to turn it off.
