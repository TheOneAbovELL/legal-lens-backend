# Contributing

## Workflow

* `main` is protected: changes land through pull requests after the CI workflow (backend, frontend,
  E2E) passes. Keep the branch up to date with `main` before merging.
* Branch names: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`.
* Commits: present tense, one logical change each; explain *why* in the body when it is not obvious.
* Pull requests use the template; fill the checklist honestly (a skipped item is fine when stated).

## Local setup

See [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md). Short version:

```bash
python -m venv venv && source venv/bin/activate      # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                                  # set GROQ_API_KEY
uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

## Before you push

```bash
ruff check app scripts tests && pytest -q
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
python scripts/export_openapi.py        # when a schema or router changed
cd frontend && npm run test:e2e         # when the UI changed
```

## Principles that reviews enforce

1. One canonical pipeline: chat, streaming and search go through `app/graph`; no second RAG path.
2. No fake success: no placeholder answers, zero vectors, simulated streaming or invented citations.
3. Secrets stay in the environment; nothing secret in code, docs, tests, fixtures or the frontend.
4. Frontend contracts mirror `app/schemas`; the contract test must pass against the exported OpenAPI.
5. Evidence first: anything the assistant states must be traceable to a retrieved passage.
6. Legal information, not legal advice: guardrail language and the safety gate are not optional.
