# Architecture

Modular monolith (per the Legal Lens system design): one FastAPI process, clear layers, external
managed services for vectors (Qdrant), graph (Neo4j, optional) and LLM inference (Groq).

```
API (app/api)            thin routers, DI, auth, rate limit, errors, SSE
  │
Orchestration (app/graph) LangGraph StateGraph — the only RAG pipeline
  │
Services (app/services, app/rag)   query understanding, retrieval, reranking, fusion,
  │                                safety, mapping, generation/validation, ingestion, evaluation
Domain (app/domain)       pydantic models: documents, chunks, queries, evidence, citations
  │
Providers (app/providers) Qdrant store, embeddings, LLM providers + router, Neo4j client
Core (app/core)           settings, logging, exceptions, retry, security, text utils
```

Rules enforced by the layout:

* Routers never touch Qdrant, embeddings, prompts or chunking — they build `PipelineOptions` and
  call `PipelineService`.
* Graph nodes (`app/graph/nodes.py`) are adapters: they call services and return partial state.
* Only `app/providers/vector_store/qdrant_store.py` imports `qdrant_client`; only
  `app/providers/llm/groq_provider.py` imports `groq`.
* Every long-lived resource (models, clients, compiled graph) is built once in `app/container.py`
  during the FastAPI lifespan and injected; tests inject fakes through the same constructor.

## Request flow

```
POST /api/v1/chat ─▶ validation ─▶ PipelineService.run / .stream
  understand (normalise, entities, MEM-0 follow-up, intent)
  safety ──refuse──▶ redirect message (no retrieval, no LLM)
         └small_talk─▶ canned reply
  classify (complexity → retrieval profile → route)
  plan_simple | plan_moderate (expansion) | plan_complex (decomposition)
  retrieve (dense ∥ sparse ∥ metadata ∥ graph, per sub-query, RRF fusion)
  rerank (per sub-query) ─▶ fuse (budgeted context, C# citations)
  map_provisions (IPC↔BNS, M# citations) ─▶ validate_evidence
     ├─ search mode ─▶ END
     ├─ insufficient ─▶ "cannot answer from sources" (no LLM)
     └─ generate (real token streaming) ─▶ validate_answer ─(invalid, once)─▶ generate
```

## Persistence

* **Qdrant** — chunks with named dense (`dense`, 1024-d cosine) and sparse (`sparse`, IDF modifier)
  vectors and full chunk metadata payload. Cloud/server (`QDRANT_URL`) or embedded (`QDRANT_PATH`).
* **SQL** (SQLite default, PostgreSQL via `DATABASE_URL`) — `users` only, managed by Alembic.
  Conversations are deliberately not persisted (MoM: MEM-0 is non-persistent).
* **Neo4j** — optional; used for statute lookup and REPLACED_BY cross-checks. Guarded by a per-call
  timeout and a circuit breaker so an outage costs one timeout per cooldown window.

## Failure handling

Structured `AppError` subclasses (`app/core/exceptions.py`) map to consistent JSON errors with a
request ID; internal details are logged, never returned. Optional sources (graph, one retriever)
degrade with warnings; required failures (all retrievers, LLM chain) surface as 502/503.
