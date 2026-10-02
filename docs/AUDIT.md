# Repository audit (pre-rebuild baseline, 2026-10-02)

This audit was produced before the frontend / conversation-persistence rebuild, as required by the
master rebuild prompt. It is written against the *code*, not the historical documents.

## A. Current architecture

```
HTTP (FastAPI) ─ app/api/v1/*  ──► app/services/* ──► app/graph (LangGraph, 16 nodes)
                                                   │
      app/container.py builds everything once      ├─► app/rag/* (query understanding, hybrid retrieval,
      in the lifespan and injects it via            │             fusion, reranking, context, evaluation)
      request.app.state.container                   └─► app/providers/* (Groq LLM, bge-m3 embeddings,
                                                                          Qdrant, optional Neo4j)
app/db (SQLAlchemy async + Alembic)  — users only
```

* One compiled graph serves `POST /api/v1/chat`, `POST /api/v1/chat/stream`, the deprecated
  `/api/v1/query/stream`, `POST|GET /api/v1/search` and `POST /api/v1/diagnostics/route`.
* No import-time model or client construction (`app/main.py` builds the app object only).

## B. Current request lifecycle (chat)

`RequestContextMiddleware` (request id, body limit) → rate limit → optional bearer auth →
`check_query` → `PipelineService.run|stream` → graph: `understand` → `safety` → `classify` →
`plan_simple|plan_moderate|plan_complex` → `retrieve` → `rerank` → `fuse` → `map_provisions` →
`gate_evidence` → `generate` → `validate_answer` (one bounded regeneration) → `finalize`; refusals,
small talk and insufficient evidence are terminal nodes. SSE uses LangGraph `updates` + `custom`
stream modes (real provider deltas).

## C. Current frontend state

**None.** No TypeScript/JavaScript, no `frontend/` directory, no static assets. The API was only
exercised through Swagger, curl scripts and Python scripts.

## D. Current backend state

Working and verified against a running server (see `docs/TESTING.md`): health/readiness, auth
(bcrypt + JWT, signup/login/me), chat JSON + SSE, search, statute mapping, diagnostics (dev only),
structured error envelope, request ids, structured logging with redaction, rate limiting, body
limits, Pydantic settings with production validation.

Gaps against the target product:

| Gap | Impact |
|---|---|
| No conversation / message persistence (MEM-0 is in-process only) | history lost on restart, no sidebar |
| Chat response lacks `conversation_id`, `message_id`, `analysis`, `status` | frontend cannot reconcile streams |
| Stream ends with `done`, no `analysis`/`complete` events | contract mismatch with the spec |
| Error envelope `details` is a list, spec wants an object | minor; frontend parser must accept both |
| System prompt does not state that evidence is untrusted | prompt-injection defence incomplete |
| No CI workflow | regressions not caught on push |
| Docs missing: FRONTEND, LOCAL_DEVELOPMENT, SECURITY, ADAPTIVE_RAG | handoff incomplete |

## E. Current RAG state

Hybrid dense (bge-m3) + sparse (BM25-style, IDF in Qdrant) + exact-provision metadata (+ optional
Neo4j) → weighted RRF → lexical reranker (measured better than the ms-marco cross-encoder on the
fixture set) → context builder with pinning, per-sub-query floors, dedup and budgets → evidence
gate → grounded generation → citation validation. Evaluation framework and 18 labelled fixture
queries exist; the real corpus is not ingested yet.

## F. Database / vector-store state

* SQLite (`data/legal_lens.db`) by default, PostgreSQL via `DATABASE_URL`; Alembic migration
  `0001_create_users` only.
* Qdrant: embedded `data/qdrant` locally (Qdrant Cloud refused connections on 2026-10-02 and is
  commented out in `.env`); named `dense` + `sparse` vectors, payload mapping documented in
  `docs/RAG.md`; collection creation is opt-in (`QDRANT_CREATE_COLLECTION`), never destructive.

## G. Auth state

Real: bcrypt hashes, signed HS256 JWT with issuer and expiry, generic 401 on bad credentials,
`AUTH_REQUIRED` toggles enforcement on chat/search/statute. Bearer tokens (no cookie session).
Trade-off recorded in `docs/SECURITY.md`.

## H. Current tests

175 passing, 4 live tests opt-in (`LIVE_TESTS=1`, `MODEL_TESTS=1`): unit, rag, graph (node-level +
routing), api (HTTP through the real app + OpenAPI), integration (legacy collection, lock
handling), evaluation. All fakes live under `tests/` only.

## I. Deployment state

Dockerfile (non-root, healthcheck, optional model preload), docker-compose (api + optional Qdrant
server), Procfile + runtime.txt for buildpack hosts. Docker is not installed on this machine, so
the image build is untested here.

## J. Duplicate / obsolete modules

Removed in the previous phase: `app/embeddings`, `app/langgraph`, `app/rag/{generator,pipeline,
retriever}.py`, old `app/services/*`, old routers, stray `git` file. A repository search for
imports of the deleted modules returns nothing. Scratch files `test_qdrant.py`, `test_rag.py`
and `notepad test_qdrant.py` in the root are the developer's and are git-ignored.

## K. Missing components

Frontend (entire), conversations (models, migration, repository, service, API), chat/stream
contract fields, CI, E2E tests, docs listed in D.

## L. Risk register

| Risk | Mitigation |
|---|---|
| Qdrant Cloud / Neo4j unreachable | embedded Qdrant + graph disabled; readiness reports both truthfully |
| Embedded Qdrant allows one process | documented; `verify_backend.py --server` for a running server |
| Small paraphrased fixture corpus | quality numbers are fixture-only; real corpus is the benchmark |
| Classifier accuracy 66.7 % on 18 queries | weights live in JSON; re-tune on the real set |
| gpt-oss reasoning consumes budget | `include_reasoning=false`, low effort, enforced in provider |
| Historical secrets in `.env` | treated as compromised; `.env` ignored; never printed |

## M. Migration plan

1. Branch `rebuild/production`, checkpoint the verified backend.
2. Conversations: models + migration `0002`, repository, `ConversationService`, `ChatService`
   (persistence around the pipeline), API, ownership tests.
3. Contract: `conversation_id`/`message_id`/`analysis`/`status` on chat; `analysis` and
   `complete` SSE events; prompt-injection clause + adversarial test.
4. Frontend (`frontend/`, React + TypeScript + Vite): auth, workspace, chat with streaming,
   evidence panel, search, BNS mapping card, conversations sidebar, diagnostics page.
5. Frontend tests (Vitest + Testing Library), E2E (Playwright against a deterministic test
   server), CI workflow, docs, final verification with both servers running.

## N. Final folder structure (decision)

The backend stays at the repository root (`app/`, `tests/`, `scripts/`, `docs/`) rather than
moving under `backend/`: the existing deploy files (`Procfile`, `Dockerfile`, `runtime.txt`),
the developer's established `uvicorn app.main:app --reload` workflow and every path in the
docs depend on it, and a rename adds churn without architectural value. The frontend lives in
`frontend/` as a first-class part of the same repository.

## O. API contract

See `docs/API.md` (updated with conversations, the new chat fields and the SSE event list).

## P. Frontend screens

Login / signup, workspace (sidebar + chat + evidence panel), search explorer, source viewer,
BNS mapping card inside chat, account menu, development diagnostics page.

## Q. External dependencies still required

| Dependency | Needed for | Status |
|---|---|---|
| Qdrant collection with the real corpus | retrieval | embedded local index with fixtures only |
| Groq API key | generation, LLM decomposition | configured |
| PostgreSQL (optional) | multi-instance persistence | SQLite used locally |
| Neo4j (optional) | graph retriever | disabled |
