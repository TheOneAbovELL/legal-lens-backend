# Local development

Two processes: the FastAPI backend (repository root) and the Vite frontend (`frontend/`). The
frontend dev server proxies API calls to the backend, so nothing needs editing to connect them.

## Prerequisites

Python 3.12, Node 20+ (22 recommended), git. Optional: Docker, a Groq API key (answers), a Qdrant
Cloud cluster (otherwise the embedded local index under `data/qdrant` is used).

## One command: `start.sh`

```bash
./start.sh            # prepare + start backend and frontend; Ctrl+C stops both
./start.sh stop       # stop them from another terminal
./start.sh status     # what is running, and the /ready verdict
```

It checks Python 3.11+ / Node 20+ / curl, creates `venv` and installs requirements when missing,
installs `frontend/node_modules` when missing or outdated, creates `.env` from `.env.example` if
absent, builds the local index from `data/legal_docs` on first run (embedded mode only), starts
uvicorn (`--reload`) and Vite, waits for `/health` and the frontend, waits for `/ready` while the
embedding model loads, then opens http://localhost:5173. Logs go to `logs/backend.log` and
`logs/frontend.log`. Servers that are already running are reused, never killed.

Windows: run it from **Git Bash**. In PowerShell, plain `bash` is usually WSL, which cannot use the
Windows virtualenv, so call Git's bash: `& "C:\Program Files\Git\bin\bash.exe" start.sh`.

Options: `BACKEND_PORT`, `FRONTEND_PORT`, `LL_NO_BROWSER=1`, `LL_NO_RELOAD=1`, `LL_SKIP_INSTALL=1`,
`LL_KEEP_SHELL_ENV=1` (by default a stray `QDRANT_URL`/`QDRANT_API_KEY` in your shell is ignored so
`.env` decides), `LL_INGEST_FIXTURES=1` (also index the demo statutes on first run),
`LL_READY_TIMEOUT` (seconds). Example: `BACKEND_PORT=8001 LL_NO_BROWSER=1 ./start.sh`.

The manual steps below do the same thing by hand.

## Backend

Windows (PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
Copy-Item .env.example .env        # then set GROQ_API_KEY (or LLM_API_KEY); leave QDRANT_URL empty for local mode
python scripts/ingest.py           # index documents from data/legal_docs (and/or evaluation/corpus)
uvicorn app.main:app --reload      # http://127.0.0.1:8000  (docs at /docs)
```

Ubuntu / macOS:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
python scripts/ingest.py
uvicorn app.main:app --reload
```

The first start downloads `BAAI/bge-m3` (~2.3 GB) into the Hugging Face cache; `/ready` returns
503 with `embedding: loading` until it is in memory.

## Frontend

```bash
cd frontend
npm install
cp .env.example .env               # optional; defaults proxy to http://127.0.0.1:8000
npm run dev                        # http://localhost:5173
```

Open http://localhost:5173, create an account, ask a question. The Diagnostics tab (dev only)
shows readiness, index, embedding, LLM and routing state.

## Offline frontend development (no models, no keys)

`python scripts/e2e_server.py --port 8011` runs the real application with the test doubles
(in-memory index with the fixture statutes, scripted LLM, temp database). Point the dev server at
it: `VITE_DEV_PROXY_TARGET=http://127.0.0.1:8011 npm run dev` (PowerShell:
`$env:VITE_DEV_PROXY_TARGET="http://127.0.0.1:8011"; npm run dev`).

## Tests

| What | Command |
|---|---|
| Backend (offline, deterministic) | `pytest -v` |
| Backend live services (opt-in) | `LIVE_TESTS=1 MODEL_TESTS=1 pytest tests/live -v` |
| Frontend unit/component/contract | `cd frontend && npm test` |
| Frontend lint / typecheck / build | `npm run lint && npm run typecheck && npm run build` |
| Browser journeys | `cd frontend && npx playwright install chromium && npm run test:e2e` |
| Running server checks | `python scripts/verify_backend.py --server http://127.0.0.1:8000`, `python scripts/smoke_test.py` |
| Contract export | `python scripts/export_openapi.py` (commit `frontend/contract/openapi.json`) |

## Both servers with Docker

```bash
docker compose up --build          # frontend http://localhost:8080, API http://localhost:8000
```

## Common problems

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: qdrant_client` / `uvicorn not recognized` | virtualenv not activated |
| `WinError 10013` on port 8000 | another process holds the port (`Get-NetTCPConnection -LocalPort 8000`) |
| ingest connects to a remote Qdrant although `.env` is local | a `QDRANT_URL` variable in the shell overrides `.env`: `Remove-Item Env:QDRANT_URL, Env:QDRANT_API_KEY` |
| `/ready` says `qdrant: unavailable … already accessed by another instance` | the embedded index is open in another process (ingest/verify while the server runs); stop one, readiness recovers automatically |
| frontend shows "backend unavailable" | backend not running or wrong `VITE_DEV_PROXY_TARGET` |
| E2E web server timeout | `..\venv\Scripts\python.exe` missing: set `E2E_PYTHON` to your interpreter |
