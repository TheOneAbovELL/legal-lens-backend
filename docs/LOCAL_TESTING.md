# Local testing guide

Everything below runs against the real application. PowerShell commands are shown; on
Linux/macOS use `source venv/bin/activate` and the same Python/curl commands.

## 1. Activate the environment

```powershell
cd "C:\Users\omjee\OneDrive\Desktop\LEGAL LENS BACKEND"
.\venv\Scripts\Activate.ps1          # prompt shows (venv)
```

Without activation, `python` is the system interpreter (`No module named 'qdrant_client'`) and
`uvicorn` is not found.

## 2. Install dependencies (first time / after requirements change)

```powershell
pip install -r requirements-dev.txt
```

## 3. Configure `.env`

```powershell
copy .env.example .env               # first time only, then edit
```

Minimum for local use: `GROQ_API_KEY` (or `LLM_API_KEY`). Leave `QDRANT_URL` empty to use the
embedded store in `data\qdrant`. Environment variables override `.env`: if a shell has an old
`QDRANT_URL`, clear it with `Remove-Item Env:QDRANT_URL, Env:QDRANT_API_KEY -ErrorAction SilentlyContinue`.

Index documents (run while the server is **stopped** — the embedded store allows one process):

```powershell
python scripts/ingest.py --source data/legal_docs
python scripts/ingest.py --source evaluation/corpus     # optional demo statutes (paraphrased fixtures)
```

The demo statutes have document IDs starting `fixture-`; to start clean, stop the server and delete
`data\qdrant`, then re-ingest.

## 4. Start the server

```powershell
uvicorn app.main:app --reload
```

The banner prints the URLs and each initialisation step; the embedding model loads in the background
(`/ready` returns 503 with `embedding=loading` for ~30–60 s on first start).

## 5. Open Swagger

| What | URL |
|---|---|
| Swagger UI (interactive) | http://127.0.0.1:8000/docs |
| ReDoc | http://127.0.0.1:8000/redoc |
| OpenAPI JSON | http://127.0.0.1:8000/openapi.json |
| Health | http://127.0.0.1:8000/health |
| Readiness | http://127.0.0.1:8000/ready |

In Swagger: expand an endpoint → **Try it out** → pick an example from the **Examples** dropdown →
**Execute**. Request bodies include ready-made examples for every route.

## 6. Health and readiness

* `GET /health` → `{"status": "healthy"}` (process alive; never depends on external services).
* `GET /ready` → `status: ready` (200) or `not_ready` (503) with `failed` naming the component and
  `components[].error` saying why (e.g. locked embedded store, missing collection, no LLM key).

## 7. Authenticate (optional unless `AUTH_REQUIRED=true`)

1. `POST /api/v1/auth/signup` (example "citizen") → 201 with `access_token`
   (or `POST /api/v1/auth/login` for an existing user).
2. Click **Authorize** (top right), paste the token **without** `Bearer `, Authorize.
3. `GET /api/v1/auth/me` → your user. The token persists across page reloads.

## 8. Verify components (Diagnostics tag)

* `GET /api/v1/diagnostics/config` — active models/providers/features (no secrets).
* `GET /api/v1/diagnostics/qdrant` — connectivity, collection, dimension, distance, sparse vectors,
  points, indexed chunk profiles, read-only probe query.
* `GET /api/v1/diagnostics/embedding` — embeds a probe: dimension, finite, non-zero, L2 norm ≈ 1.
* `POST /api/v1/diagnostics/llm` — one minimal request through the retry/fallback chain (costs a few tokens).
* `POST /api/v1/diagnostics/route` — intent, safety, complexity (+ reasons), profile, route and the
  planned sub-queries, without retrieval or generation.

## 9. Search (no LLM)

`POST /api/v1/search` with `{"query": "Section 302 IPC", "top_k": 5}`. Check `diagnostics`:
`retrieval_mode: "hybrid"`, `sources.dense/sparse/metadata.executed` with hit counts, `fusion.count`,
`reranking.method/count`, `context.selected_chunks`, `latency_ms`. `generation.executed` is false.

## 10–12. SIMPLE / MODERATE / COMPLEX

Use `POST /api/v1/diagnostics/route` (instant, no LLM) and then `POST /api/v1/chat` with the same
examples (dropdown):

| Query | Expected route | Profile | Sub-queries |
|---|---|---|---|
| `What is Article 21?` | simple | FAST | 1 |
| `Explain the difference between Article 14 and Article 21.` | moderate | BALANCED | original + one look-up per article |
| `Compare the legal consequences under IPC and BNS, identify the corresponding provisions, analyze how the change affects an accused person, and cite the relevant authorities.` | complex | DEEP | up to 5 (chat uses the LLM planner, route diagnostics the rule planner) |
| `Will I win my case?` | refuse | – | 0 (no retrieval, no LLM) |

In chat responses, `metadata.complexity.reasons`, `metadata.subqueries` and `diagnostics` show what
ran; `citations` lists only evidence the answer actually cited.

## 13. Streaming

```powershell
python scripts/test_stream.py "Compare IPC 420 and BNS 318 and explain the impact on an accused"
python scripts/test_stream.py --raw "What is Article 21?"        # raw JSON events
```

Swagger can call `POST /api/v1/chat/stream`, but it buffers SSE and shows events only at the end;
use the script (or `curl -N`) to watch tokens arrive.

## 14. curl scripts (Git Bash / WSL)

```bash
./scripts/test_health.sh
./scripts/test_ready.sh
./scripts/test_auth.sh            # prints: export LEGAL_LENS_TOKEN=...
./scripts/test_search.sh "Section 302 IPC" 5
./scripts/test_chat.sh "What is the punishment for theft?"
./scripts/test_stream.sh "Explain Article 21"
BASE_URL=http://127.0.0.1:9000 ./scripts/test_health.sh   # other host/port
```

## 15. Automated tests (no server, network or credentials needed)

```powershell
pytest -v
pytest tests/unit -v
pytest tests/rag -v
pytest tests/graph -v
pytest tests/api -v
pytest tests/integration -v
pytest tests/evaluation -v
$env:LIVE_TESTS = "1"; pytest tests/live -v; Remove-Item Env:LIVE_TESTS     # real Groq + configured Qdrant (read-only)
$env:MODEL_TESTS = "1"; pytest tests/live -v; Remove-Item Env:MODEL_TESTS   # real embedding model
```

## 16. Smoke test and full verification

```powershell
python scripts/smoke_test.py                                     # against the running server
python scripts/verify_backend.py --server http://127.0.0.1:8000  # 18 checks against the running server
python scripts/verify_backend.py                                 # in-process (stop uvicorn first if Qdrant is embedded)
```

`BLOCKED` means an external dependency (LLM key, Qdrant) is unavailable — never reported as PASS.

## 17. RAG evaluation

```powershell
python scripts/evaluate_rag.py                       # retrieval + routing + safety through the real pipeline (no LLM)
python scripts/evaluate_rag.py --with-answers        # + answer rate, citation validity (one LLM call per query)
python scripts/evaluate_rag.py --reranker cross_encoder    # A/B a reranker
python scripts/evaluate_chunking.py --strategies fixed sentence recursive semantic hierarchical --top-k 5 10
python scripts/evaluate_safety.py
```

Evaluation uses an isolated in-memory index; your `data\qdrant` is never modified.

## 18. Shut down

Press **Ctrl+C** in the uvicorn terminal. The log ends with `Shutdown complete.` after closing the LLM,
vector store, database and graph clients. If port 8000 is still busy (`WinError 10013`), find the process:
`Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess`.
