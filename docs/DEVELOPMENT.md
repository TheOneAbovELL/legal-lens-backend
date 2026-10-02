# Development

Requirements: Python 3.11–3.13 (validated on 3.13), ~3 GB disk for BGE-M3 on first use.

```bash
python -m venv venv
venv/Scripts/activate            # Linux/macOS: source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Without `QDRANT_URL`, an embedded Qdrant is stored in `./data/qdrant` (single process only). Without
an LLM key, retrieval and search work and `/ready` reports the LLM as not configured.

```bash
python scripts/ingest.py --source data/legal_docs
python scripts/ingest.py --source evaluation/corpus          # optional fixture statutes for local testing
uvicorn app.main:app --reload
```

## Tests

```bash
pytest                       # unit, rag, graph, api, evaluation — no network or credentials
ruff check app scripts tests alembic
```

Tests build a real `Container` with in-memory Qdrant, a temporary SQLite DB, a deterministic hashing
embedder and a scripted LLM (`tests/fakes.py`), and ingest `evaluation/corpus`.

Layout: `tests/unit` (config, security, entities, intent, complexity, safety, memory, mapping, LLM
router, Neo4j circuit), `tests/rag` (documents, all chunkers, retrievers, hybrid fusion, reranking,
context fusion, decomposition, validation, ingestion/versioning), `tests/graph` (routing, refusal,
evidence gate, regeneration, streaming, errors, memory), `tests/api` (HTTP contracts, SSE, auth,
rate limits, size limits, error hygiene), `tests/evaluation` (metrics, judging, runner, selector).

## Conventions

* Add a new LLM vendor: implement `LLMProvider` and register it in `app/providers/llm/factory.py`.
* Add a chunking strategy: subclass `ChunkingStrategy`, register in `chunking/registry.py`, add a
  profile to `config/chunking_profiles.json`, evaluate it before making it the default.
* Add a migration: `alembic revision -m "..."` then edit `alembic/versions/`.
* Settings: add to `app/core/config.py` and `.env.example`; nothing else reads environment variables.
