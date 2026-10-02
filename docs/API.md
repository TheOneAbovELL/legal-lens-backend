# API (v1)

Interactive docs: `/docs` (disabled in production). Machine-readable contract:
`frontend/contract/openapi.json` (`python scripts/export_openapi.py`). All errors:

```json
{"error": {"code": "not_found", "message": "Conversation not found.", "request_id": "…", "details": [...]}}
```

| Status | Codes |
|---|---|
| 401 | `authentication_failed` (missing/invalid/expired token, bad credentials) |
| 403 | `forbidden` (registration disabled) |
| 404 | `not_found` (unknown route, diagnostics off, conversation not owned by the caller) |
| 409 | `conflict` (username/email taken) |
| 413 | `payload_too_large` |
| 422 | `validation_error`, `invalid_query` (empty/too long query, unsupported code) |
| 429 | `rate_limited` (+ `Retry-After`) |
| 502 | `llm_provider_error` |
| 503 | `vector_store_error`, `retrieval_error`, `embedding_error`, `not_ready` |
| 504 | `timeout` |
| 500 | `internal_error` (never a traceback) |

Every response carries `X-Request-ID`. With `AUTH_REQUIRED=true`, chat/search/statute endpoints
need `Authorization: Bearer <token>`; conversation endpoints always do.

## Health
* `GET /` — `{"status": "ok", "service": "legal-lens-backend", "version": "...", "docs": "/docs"}`.
* `GET /health` — liveness `{"status": "healthy"}`; never depends on external services.
* `GET /ready` — `{"status": "ready" | "not_ready", "checks": {"application", "embedding", "qdrant",
  "database", "llm", "knowledge_graph"}, "failed": [...], "components": [...]}`; 503 when a required
  component is unusable. No LLM call is made; the knowledge graph never blocks readiness.

## Auth
* `POST /api/v1/auth/signup` `{username, email?, password (8–72 bytes, not all letters/digits), role}` → 201 + token
  (403 when `AUTH_ALLOW_REGISTRATION=false`; 409 if taken).
* `POST /api/v1/auth/login` `{username (or email), password}` → `{message, user, role, access_token, token_type, expires_in}`; 401 on failure.
* `GET /api/v1/auth/me` → `{id, username, email, role, created_at}`.

## Chat
`POST /api/v1/chat` (also `/api/v1/chat/`, the original path)

```json
{"query": "...", "conversation_id": "optional (alias: session_id)", "user_role": "citizen|advocate|researcher",
 "profile": "FAST|BALANCED|DEEP", "filters": {...}, "stream": false}
```

Persistence: with a bearer token the exchange is stored — omit `conversation_id` to create a
conversation titled from the question (its id is returned), or pass one you own (404 otherwise).
Anonymous requests are stateless; `conversation_id` then only keys MEM-0 follow-ups.

Response:

| Field | Meaning |
|---|---|
| `answer`, `source` | grounded answer with `[C#]`/`[M#]` citations; legacy `source` = `qdrant` / `none` |
| `request_id` | correlates with logs and `X-Request-ID` |
| `conversation_id`, `message_id`, `persisted` | persisted ids (null / false when stateless) |
| `status` | `complete` · `refused` · `insufficient_evidence` · `small_talk` |
| `analysis` | `intent`, `complexity`, `confidence`, `route`, `retrieval_profile`, `safety_decision`, `jurisdiction`, `outside_jurisdiction`, `decomposition_needed`, `comparison_required`, `provisions[]`, `follow_up` |
| `refused` | safety guard redirected the request |
| `citations[]` | only evidence actually cited: `citation_id`, `document_id`, `document_version`, `title`, `act`, `section`, `section_heading`, `subsection`, `paragraph`, `page`, `case_name`, `court`, `source`, `chunk_id`, `retrieval_sources`, `score`, `excerpt` |
| `bns_alerts[]` | `old`, `new`, `effective`, `mapping_type` (exact / approximate / ambiguous / no_mapping / unknown), `subject`, `notes`, `verification_status`, `provenance` |
| `warnings[]`, `disclaimer` | |
| `metadata` | intent, safety, complexity + reasons, route, profile, sub-queries, retrieval source counts, reranker, evidence/context sizes, output validation, provider, model, attempts, token usage, per-stage timings, latency, errors (trimmed in production) |
| `diagnostics` | per-stage execution facts (non-production only; see below) |

### Streaming
`stream: true`, `Accept: text/event-stream`, or `POST /api/v1/chat/stream`. Server-Sent Events,
one JSON object per `data:` line with a `type`:

| Event | Payload |
|---|---|
| `start` | `request_id`, `conversation_id`, `persisted`, `user_message_id` |
| `intent` | `intent`, `confidence`, `entities[]`, `follow_up` |
| `safety` | `decision`, `categories[]` |
| `complexity` | `complexity`, `confidence`, `reasons[]`, `profile`, `route` |
| `analysis` | the `QueryAnalysis` object (same as the JSON `analysis` field) |
| `plan` | `method`, `subqueries[] {id, query, purpose}` |
| `retrieval` | `candidates`, `sources {dense, sparse, metadata, graph}` |
| `reranking` | `reranker`, `count` |
| `evidence` | `count`, `context_tokens`, `citations[]` (selected context) |
| `bns_alert` | `mappings[]` |
| `token`* | `content` (real provider delta), `attempt` (a new number = regeneration restarted) |
| `citation`* | a `Citation` actually cited by the final answer |
| `validation` | `valid`, `warnings[]`, `invalid_citation_ids[]` |
| `complete` | the full JSON response plus `status`, `message_id`, `conversation_id`, `persisted` |
| `error` | `code`, `message`, `request_id` |

The stream always ends with `complete` or `error`. Refusals / insufficient-evidence / small-talk
replies are fixed messages delivered as a single `token` event. No reasoning or prompts are streamed.
If the client disconnects mid-stream, a persisted assistant message is stored as `incomplete` with
the text streamed so far.

`POST /api/v1/query/stream` — deprecated legacy endpoint: plain-text answer tokens only.

## Conversations (bearer token required; scoped to the caller)
* `GET /api/v1/conversations?limit=` → `{conversations: [{id, title, created_at, updated_at, archived_at}], total}` (most recent first).
* `POST /api/v1/conversations` `{title?}` → 201 conversation.
* `GET /api/v1/conversations/{id}` → conversation + `messages[]` (`id`, `role`, `content`, `status`
  (`complete` · `refused` · `insufficient_evidence` · `small_talk` · `failed` · `incomplete`), `request_id`,
  `complexity`, `intent`, `created_at`, `citations[]` stored with the message so history renders without the index).
* `GET /api/v1/conversations/{id}/messages` → `messages[]`.
* `PATCH /api/v1/conversations/{id}` `{title}` → conversation.
* `DELETE /api/v1/conversations/{id}` → 204 (messages and stored citations are deleted).

Another user's conversation is a 404 for every method (existence is never leaked).

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
sources, candidates, latency, timings), `diagnostics`. Legacy `POST /api/v1/search?query=...` and
`GET /api/v1/search?query=...&top_k=` are supported.

## Statutes
`GET /api/v1/statute/map?code=IPC&section=304A` → a `BnsAlert`. Codes: IPC, BNS, CrPC, BNSS, IEA, BSA.

## Diagnostics (non-production; 404 when `DIAGNOSTICS_ENABLED=false` or `APP_ENV=production`)
* `GET /api/v1/diagnostics/config` — effective configuration without secrets.
* `GET /api/v1/diagnostics/qdrant` — collection, dimension, distance, sparse config, points, profiles, read-only probe query.
* `GET /api/v1/diagnostics/embedding` — embeds a probe; dimension, finite, non-zero, L2 norm.
* `POST /api/v1/diagnostics/llm` — `{"prompt": "Respond with OK.", "max_tokens": 64}`; one minimal call.
* `POST /api/v1/diagnostics/route` — `{"query": "...", "use_llm_decomposition": false}`; intent, safety,
  complexity, profile, route and planned sub-queries without retrieval or generation.

Chat and search responses also carry `diagnostics` in non-production environments:

```json
{"complexity": "COMPLEX", "retrieval_profile": "DEEP", "route": "complex", "retrieval_mode": "hybrid",
 "subqueries": [...],
 "sources": {"dense": {"executed": true, "hits": 32, "latency_ms": 118}, "sparse": {...}, "metadata": {...}, "graph": {"executed": false, "hits": 0}},
 "fusion": {"executed": true, "count": 41, "method": "weighted reciprocal rank fusion"},
 "reranking": {"executed": true, "count": 41, "method": "lexical"},
 "context": {"executed": true, "selected_chunks": 8, "groups": 4, "context_tokens": 1900, "dropped_duplicates": 3, "dropped_low_relevance": 20, "dropped_budget": 0},
 "provision_mapping": {"executed": true, "count": 2}, "generation": {"executed": true, "count": 1, "method": "groq:openai/gpt-oss-120b"},
 "latency_ms": {"understand": 0.4, "retrieval": 140.2, "rerank": 3.1, "generation": 2100.0, "total": 2300.5}}
```

Every value is derived from what actually ran, never from configuration.

## Changes from the previous API
| Before | Now |
|---|---|
| `/auth/login` returned `{"message": "Invalid credentials"}` with 200 for admin/admin | real users, bcrypt, signed JWT; invalid → 401 |
| `/chat/` returned `{answer, source}` | same fields plus status, analysis, citations, alerts, persistence ids, metadata; JSON or SSE |
| stream ended with `done` | ends with `complete` (adds `analysis` event and ids) |
| `/search` took `?query=` and returned zero-vector results with `"answer": "Generated later"` | JSON body (query param still accepted), structured results |
| `/query/stream` streamed a template string | deprecated; streams real LLM tokens |
| no history | `/api/v1/conversations` (owner-scoped, with stored citations) |
