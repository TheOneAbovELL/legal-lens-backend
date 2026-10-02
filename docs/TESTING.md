# Testing

## Layers

| Layer | Location | Needs | Run |
|---|---|---|---|
| Unit | `tests/unit` | nothing | `pytest tests/unit -v` |
| RAG components | `tests/rag` | nothing (in-memory Qdrant, hashing embedder) | `pytest tests/rag -v` |
| Graph (nodes + routing + end-to-end) | `tests/graph` | nothing (scripted LLM) | `pytest tests/graph -v` |
| API (HTTP through the real app) | `tests/api` | nothing | `pytest tests/api -v` |
| Integration | `tests/integration` | nothing (legacy collection, store locking) | `pytest tests/integration -v` |
| Evaluation framework | `tests/evaluation` | nothing | `pytest tests/evaluation -v` |
| Live services | `tests/live` | `LIVE_TESTS=1` (Groq key, configured Qdrant read-only), `MODEL_TESTS=1` (real bge-m3) | `pytest tests/live -v` |
| Running server | `scripts/smoke_test.py`, `scripts/verify_backend.py --server URL`, `scripts/test_stream.py`, `scripts/test_*.sh` | a running server | see LOCAL_TESTING.md |
| Pipeline evaluation | `scripts/evaluate_rag.py`, `scripts/evaluate_chunking.py`, `scripts/evaluate_safety.py` | embedding model (+ LLM for `--with-answers`) | see EVALUATION.md |

Test configuration lives in fixtures (`tests/conftest.py`) rather than a `.env.test` file: every test
builds `Settings(_env_file=None, ...)` with an in-memory Qdrant collection, a temporary SQLite
database, `HashingEmbedder` and `ScriptedLLM` (`tests/fakes.py`). `conftest.py` also removes any
setting-related environment variables (e.g. a stray `QDRANT_URL`) from the test process, so results do
not depend on the developer's shell. Fakes exist only under `tests/`; the application never uses them.

## Component matrix

✓ = covered, – = not applicable. "Live" = verified against real services by `tests/live` or the
scripts against a running server.

| Component | Unit | Integration (in-process) | API | Live |
|---|---|---|---|---|
| Configuration / secrets in reprs and logs | ✓ test_config | – | ✓ diagnostics/config has no secrets | ✓ verify_backend #2 |
| FastAPI app, lifespan, middleware, errors | – | ✓ | ✓ test_api, test_openapi | ✓ smoke, verify |
| OpenAPI / Swagger / ReDoc | – | – | ✓ test_openapi | ✓ verify #8 |
| Auth (bcrypt, JWT, signup/login/me) | ✓ test_security | – | ✓ test_api | ✓ smoke, verify #9 |
| Rate limit / body-size limit | ✓ | – | ✓ | – |
| Embedding provider | ✓ test_embedder (fake model) | ✓ hashing embedder | ✓ diagnostics/embedding | ✓ MODEL_TESTS, verify #10 |
| Qdrant store (create/validate/filters/versions/lock) | – | ✓ test_retrieval, test_legacy_collection | ✓ diagnostics/qdrant | ✓ LIVE_TESTS (read-only), verify #11 |
| Document loading / structure / cleaning | ✓ | ✓ test_documents_and_chunking | – | ✓ ingest script |
| Chunking (7 strategies, metadata, determinism) | ✓ | ✓ | – | ✓ evaluate_chunking |
| Dense retrieval | – | ✓ | ✓ search diagnostics | ✓ verify #12 |
| Sparse retrieval | ✓ encoder | ✓ | ✓ search diagnostics | ✓ verify #12 |
| Metadata (exact provision) retrieval | – | ✓ | ✓ | ✓ |
| Hybrid fusion (RRF, dedup, per-sub-query ranks) | – | ✓ | ✓ | ✓ verify #12 |
| Reranking (lexical, cross-encoder fallback) | ✓ | ✓ | ✓ | ✓ verify #13, evaluate_rag --reranker |
| Context fusion (budgets, coverage, pinning, dedup) | ✓ test_retrieval | ✓ | ✓ | ✓ |
| Query understanding (entities, intent) | ✓ | – | ✓ diagnostics/route | ✓ |
| Complexity router | ✓ | ✓ graph routing | ✓ diagnostics/route | ✓ verify #14 |
| Query expansion / decomposition | ✓ | ✓ | ✓ | ✓ live LLM planner |
| Safety guard | ✓ questionnaire 20/20 | ✓ graph refusal | ✓ | ✓ verify #15, evaluate_rag |
| IPC↔BNS mapping | ✓ test_legal_mapping | ✓ | ✓ statute/map | ✓ |
| LangGraph nodes (each) | ✓ test_nodes | ✓ test_pipeline | ✓ | ✓ verify #15 |
| LLM provider / retry / fallback | ✓ test_llm_router | ✓ | ✓ diagnostics/llm | ✓ LIVE_TESTS, verify #16 |
| Answer validation / regeneration | ✓ | ✓ | ✓ | ✓ verify #17 |
| SSE streaming | – | ✓ | ✓ | ✓ LIVE_TESTS (real deltas), verify #18, test_stream.py |
| Session memory (MEM-0) | ✓ | ✓ | ✓ | – |
| Evaluation metrics / runner | ✓ hand-computed metrics | ✓ | – | ✓ |

## Guarantees checked by tests

* No zero-vector embeddings: invalid/NaN/zero outputs raise `EmbeddingError` (test_embedder, test_llm_router).
* No fake streaming: token events are provider deltas (test_pipeline, tests/live streaming test).
* One pipeline: chat, search, both streams and diagnostics/route all use the same services/graph.
* Safety short-circuits before retrieval and generation (test_nodes, test_pipeline, verify #15).
* Search never calls the LLM (test_pipeline, test_diagnostics).
* Production hides docs/diagnostics and trims metadata (test_diagnostics).
* Automated tests never touch a real Qdrant collection, database or LLM unless `LIVE_TESTS=1`, and the
  live tests are read-only.
