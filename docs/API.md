# API (v1)

Interactive docs: `/docs` (disabled in production). All errors:
`{"error": {"code": "...", "message": "...", "request_id": "..."}}`; every response carries
`X-Request-ID`. Bodies over `MAX_REQUEST_BYTES` → 413. Rate-limited endpoints return 429 +
`Retry-After`. With `AUTH_REQUIRED=true`, chat/search/statute endpoints need `Authorization: Bearer`.

## Health
* `GET /` — `{"status": "ok", "service": "legal-lens-backend", "version": "...", "docs": "/docs"}`.
* `GET /health` — liveness `{"status": "healthy"}`; never depends on external services.
* `GET /ready` — `{"status": "ready" | "not_ready", "checks": {"application", "embedding", "qdrant",
  "database", "llm", "knowledge_graph"}, "failed": [...], "components": [...]}`; 503 when a required
  component is unusable. No LLM call is made; the knowledge graph never blocks readiness.

## Diagnostics (non-production; 404 when `DIAGNOSTICS_ENABLED=false` or `APP_ENV=production`)
* `GET /api/v1/diagnostics/config` — effective configuration without secrets.
* `GET /api/v1/diagnostics/qdrant` — collection, dimension, distance, sparse config, points, profiles, read-only probe query.
* `GET /api/v1/diagnostics/embedding` — embeds a probe; dimension, finite, non-zero, L2 norm.
* `POST /api/v1/diagnostics/llm` — `{"prompt": "Respond with OK.", "max_tokens": 64}`; one minimal call.
* `POST /api/v1/diagnostics/route` — `{"query": "...", "use_llm_decomposition": false}`; intent, safety,
  complexity, profile, route and planned sub-queries without retrieval or generation.

Chat and search responses also carry `diagnostics` in non-production environments: per-source
`executed`/`hits`/latency for dense, sparse, metadata and graph, fusion, reranking, context selection,
provision mapping, generation and per-stage latency — derived from what actually ran.

## Chat
`POST /api/v1/chat` (also `/api/v1/chat/`, the original path)

```json
{"query": "...", "session_id": "optional-mem0-id (alias: conversation_id)", "user_role": "citizen|advocate|researcher",
 "profile": "FAST|BALANCED|DEEP", "filters": {...}, "stream": false}
```

JSON response: `answer`, `source` (legacy: `"qdrant"` when answered from evidence, else `"none"`),
`request_id`, `refused`, `citations[]` (only evidence actually cited: `citation_id`, `document_id`,
`document_version`, `title`, `act`, `section`, `section_heading`, `subsection`, `paragraph`, `page`,
`case_name`, `court`, `source`, `chunk_id`, `retrieval_sources`, `score`), `bns_alerts[]`
(`old`, `new`, `effective`, `mapping_type`, `subject`, `notes`, `verification_status`, `provenance`),
`warnings[]`, `disclaimer`, `metadata` (intent, safety, complexity + reasons, route, profile,
subqueries, retrieval source counts, reranker, evidence/context sizes, output validation, provider,
model, attempts, token usage, per-stage timings, latency, errors).

### Streaming
`stream: true`, `Accept: text/event-stream`, or `POST /api/v1/chat/stream`. Server-Sent Events,
one JSON object per `data:` line:

`start` → `intent` → `safety` → `complexity` → `plan` → `retrieval` → `reranking` → `evidence` → `bns_alert` →
`token`* (real provider deltas) → `citation`* → `validation` → `done` (full result) | `error`.

Refusals / insufficient-evidence / small-talk replies are fixed messages delivered as a single
`token` event. No reasoning or prompts are streamed.

`POST /api/v1/query/stream` — deprecated legacy endpoint: plain-text answer tokens only.

## Search
`POST /api/v1/search` — retrieval only (no LLM unless `generate_answer: true`):

```json
{"query": "...", "top_k": 10, "profile": null, "generate_answer": false,
 "filters": {"document_ids": [], "document_types": ["statute"], "acts": ["IPC"], "sections": ["420"],
             "jurisdiction": "IN", "court": ["Supreme Court"], "date_from": "2020-01-01", "date_to": null}}
```

Response: `query`, `request_id`, `results[]` (`document_id`, `chunk_id`, `title`, `case_name`,
`snippet`, `content`, `score` (fusion), `rerank_score`, `relevance_score`, `retrieval_sources`,
`citation`, `metadata`, `bns_alert`), `total`, `processing_time_ms`, `answer`, `bns_alerts`,
`warnings`, `retrieval_metadata` (strategy, complexity, route, reranker, chunk_profiles, subqueries,
sources, candidates, latency, timings). Legacy `POST /api/v1/search?query=...` and
`GET /api/v1/search?query=...&top_k=` are supported.

## Statutes
`GET /api/v1/statute/map?code=IPC&section=304A` → a `BnsAlert`. Codes: IPC, BNS, CrPC, BNSS, IEA, BSA.

## Auth
* `POST /api/v1/auth/signup` `{username, email?, password (8–72 bytes, not all letters/digits), role}` → 201 + token
  (403 when `AUTH_ALLOW_REGISTRATION=false`; 409 if taken).
* `POST /api/v1/auth/login` `{username (or email), password}` → `{message, user, role, access_token, token_type, expires_in}`; 401 on failure.
* `GET /api/v1/auth/me` → current user.

## Changes from the previous API
| Before | Now |
|---|---|
| `/auth/login` returned `{"message": "Invalid credentials"}` with 200 for admin/admin | real users, bcrypt, signed JWT; invalid → 401 |
| `/chat/` returned `{answer, source}` | same fields plus citations, alerts, metadata; JSON or SSE |
| `/search` took `?query=` and returned zero-vector results with `"answer": "Generated later"` | JSON body (query param still accepted), structured results |
| `/query/stream` streamed a template string | deprecated; streams real LLM tokens |
