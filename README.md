# Legal Lens

[![CI](https://github.com/TheOneAbovELL/legal-lens-backend/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/TheOneAbovELL/legal-lens-backend/actions/workflows/ci.yml)

Evidence-grounded legal research assistant for Indian law: a FastAPI + LangGraph backend with one
canonical retrieval-augmented pipeline (Qdrant, BGE-M3, Groq) and a React/TypeScript web client,
in one repository. Every answer is built from retrieved, cited evidence that the user can inspect.

> Legal Lens provides legal *information* for education and research. It refuses outcome
> prediction, personal legal advice, litigation strategy and guilt determination, and answers only
> from retrieved, cited evidence.

```
Browser ─ React client (frontend/) ─ typed API client ─ FastAPI (app/api)
   └ application services (app/services) ─ LangGraph (app/graph)
        intent → safety → complexity → retrieval profile → dense+sparse(+metadata, graph) → fusion
        → reranking → evidence selection → IPC↔BNS mapping → context → LLM → citation validation
   └ providers: Qdrant · bge-m3 · Groq · optional Neo4j     └ SQL (users, conversations, messages, evidence)
```

## Features

| Area | What you get |
|---|---|
| Chat | streamed answers (real provider tokens), `[C1]` citation chips, evidence panel, IPC→BNS mapping cards, status row driven by backend events, stop / retry / copy |
| Conversations | persisted per user with stored citations; sidebar with rename/delete; refresh-safe |
| Search | the same hybrid retrieval engine without generation; filters by act, section, document type; source viewer |
| Routing | SIMPLE / MODERATE / COMPLEX → FAST / BALANCED / DEEP; bounded decomposition for complex questions |
| Safety | refusal gate before retrieval; jurisdiction notes; disclaimer |
| Auth | signup/login, bcrypt + JWT, owner-scoped history, generic auth errors |
| Observability | request ids, structured logs with redaction, `/ready` per dependency, stage diagnostics in non-production |
| Quality | evaluation framework (Recall/Precision@K, MRR, nDCG, citation validity, latency) with per-query reports |

## Repository layout

```
app/            backend (api, services, graph, rag, providers, db, domain, core)
alembic/        migrations (users; conversations, messages, message_evidence)
config/         chunking / retrieval profiles
data/           mappings dataset, local documents, embedded index + SQLite (git-ignored)
docs/           architecture, API, RAG, routing, security, testing, deployment …
evaluation/     labelled queries, safety questionnaire, fixture corpus, results
frontend/       React + TypeScript client (Vite), tests, Playwright E2E, Dockerfile
scripts/        ingest, evaluate_*, verify_backend, smoke_test, e2e_server, export_openapi …
tests/          backend test suite (offline by default)
```

## Quick start

Backend (Windows PowerShell; see `docs/LOCAL_DEVELOPMENT.md` for Ubuntu/macOS):

```powershell
python -m venv venv; .\venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
Copy-Item .env.example .env            # set GROQ_API_KEY; leave QDRANT_URL empty for the local index
python scripts/ingest.py --source data/legal_docs
uvicorn app.main:app --reload          # http://127.0.0.1:8000  — Swagger at /docs
```

Frontend:

```bash
cd frontend && npm install && npm run dev      # http://localhost:5173 (proxies /api to the backend)
```

Sign up, click **New chat**, ask *"What is Article 21 of the Constitution of India?"*, watch the
stream, click a citation, open the source, try Search.

## Tests and verification

```bash
pytest -v                                                  # backend: unit, rag, graph, api, integration, evaluation (offline)
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
cd frontend && npm run test:e2e                             # Playwright journeys on a deterministic backend
python scripts/verify_backend.py --server http://127.0.0.1:8000   # 18 checks against a running server
python scripts/smoke_test.py
python scripts/evaluate_rag.py --with-answers              # retrieval / routing / safety / answer metrics
```

## Configuration

Backend: `.env` (see `.env.example`). To connect production services set `QDRANT_URL`,
`QDRANT_API_KEY`, `QDRANT_COLLECTION`, `DATABASE_URL`, `LLM_API_KEY` (or `GROQ_API_KEY`),
`JWT_SECRET_KEY`, optionally `NEO4J_*`. Frontend: `frontend/.env` with `VITE_API_URL` (public,
non-secret). Nothing else needs code changes.

## Documentation

[Audit](docs/AUDIT.md) · [Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) ·
[RAG](docs/RAG.md) · [Adaptive RAG](docs/ADAPTIVE_RAG.md) · [Chunking](docs/CHUNKING.md) ·
[Query routing](docs/QUERY_ROUTING.md) · [Frontend](docs/FRONTEND.md) ·
[Local development](docs/LOCAL_DEVELOPMENT.md) · [Local testing](docs/LOCAL_TESTING.md) ·
[Testing](docs/TESTING.md) · [Evaluation](docs/EVALUATION.md) · [Security](docs/SECURITY.md) ·
[Deployment](docs/DEPLOYMENT.md) · [Development](docs/DEVELOPMENT.md)

## Important notes

* **Corpus.** `data/legal_docs/` contains a short Article 21 note; `evaluation/corpus/` holds
  *paraphrased* statute excerpts used by tests. Ingest official texts (indiacode.nic.in, SCI
  judgments) for real use — every quality number in the docs is fixture-only until then.
* **Mapping dataset.** `data/mappings/ipc_bns.json` is curated and marked `curated_unverified`.
* **Groq models.** The default is `openai/gpt-oss-120b`; configure a fallback chain with
  `LLM_PROVIDER_ORDER`.
