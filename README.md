# Legal Lens Backend

Grounded legal-information retrieval and question answering for Indian law (statutes, the
Constitution, IPC→BNS / CrPC→BNSS / IEA→BSA mappings, case law). FastAPI + LangGraph + Qdrant +
BGE-M3 + Groq, built as a modular monolith with **one** canonical RAG pipeline.

> Legal Lens provides legal *information* for education and research. It refuses outcome
> prediction, personal legal advice, litigation strategy and guilt determination, and answers only
> from retrieved, cited evidence.

## What it does

| Capability | Where |
|---|---|
| Single LangGraph pipeline (chat, search, streaming all use it) | `app/graph/` |
| Query complexity routing SIMPLE / MODERATE / COMPLEX → FAST / BALANCED / DEEP | `app/rag/query/complexity.py`, `app/rag/profiles.py` |
| Bounded query decomposition (LLM with rule-based fallback) | `app/rag/query/decomposition.py` |
| Hybrid retrieval: dense + BM25-style sparse + exact provision metadata + optional Neo4j | `app/rag/retrieval/` |
| Reranking: lexical (fast) / cross-encoder (with fallback) | `app/rag/reranking.py` |
| Context fusion with token budgets, coverage, dedup, parent expansion | `app/rag/fusion.py` |
| 7 pluggable, legal-structure-aware chunking strategies | `app/rag/chunking/` |
| Chunking evaluation framework (Recall/Precision/HitRate@K, MRR, nDCG) | `app/rag/evaluation/`, `scripts/evaluate_chunking.py` |
| IPC↔BNS provision mapping with provenance | `app/services/legal_mapping.py`, `data/mappings/ipc_bns.json` |
| Safety guard that controls routing | `app/services/safety.py` |
| Citation + answer verification with bounded regeneration | `app/services/generation.py` |
| LLM provider abstraction with retry + fallback, real streaming | `app/providers/llm/` |
| JWT auth (bcrypt), rate limiting, request-size limits, structured logs | `app/api/`, `app/core/` |
| MEM-0 short-term session memory (non-persistent) | `app/services/session_memory.py` |

## Quick start

```bash
python -m venv venv && venv/Scripts/activate        # Windows (source venv/bin/activate on Linux/macOS)
pip install -r requirements-dev.txt
cp .env.example .env                                 # set LLM_API_KEY (or GROQ_API_KEY); see below
python scripts/ingest.py --source data/legal_docs    # build the index (embedded Qdrant by default)
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`. Health: `GET /health`, readiness: `GET /ready`.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat -H "Content-Type: application/json" \
     -d '{"query": "What is the punishment under Section 420 IPC?"}'
```

Step-by-step manual testing (Swagger, auth, routing, streaming): **[docs/LOCAL_TESTING.md](docs/LOCAL_TESTING.md)**.

## Tests, verification and evaluation

```bash
pytest -v                                                  # no network / credentials / model downloads
python scripts/smoke_test.py                               # against a running server
python scripts/verify_backend.py --server http://127.0.0.1:8000   # 18-step component verification
python scripts/test_stream.py "Compare IPC 420 and BNS 318"       # watch the SSE stream
python scripts/evaluate_rag.py                             # end-to-end retrieval/routing/safety metrics
python scripts/evaluate_chunking.py --strategies fixed sentence recursive semantic hierarchical --top-k 5 10
```

## Documentation

[Architecture](docs/ARCHITECTURE.md) · [RAG pipeline](docs/RAG.md) · [Chunking](docs/CHUNKING.md) ·
[Query routing](docs/QUERY_ROUTING.md) · [API](docs/API.md) · [Evaluation](docs/EVALUATION.md) ·
[Testing](docs/TESTING.md) · [Local testing](docs/LOCAL_TESTING.md) · [Development](docs/DEVELOPMENT.md) ·
[Deployment](docs/DEPLOYMENT.md)

## Important notes

* **Corpus.** `data/legal_docs/` contains only a short Article 21 note. `evaluation/corpus/` holds
  *paraphrased* statute excerpts used for tests and evaluation — they are not authoritative text.
  Ingest official texts (indiacode.nic.in, SCI judgments) for real use.
* **Mapping dataset.** `data/mappings/ipc_bns.json` is curated and marked `curated_unverified`;
  verify entries against the official gazette before relying on them.
* **Groq models.** `llama-3.1-8b-instant` (the previous default) now returns HTTP 404 on Groq.
  The default is `openai/gpt-oss-120b`; configure a fallback chain with `LLM_PROVIDER_ORDER`.
