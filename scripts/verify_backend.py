"""Complete backend verification: the maximum safe local check of every component.

    python scripts/verify_backend.py                       # starts the REAL app in-process (your .env)
    python scripts/verify_backend.py --server http://127.0.0.1:8000   # verify a running server instead

In-process mode uses your configured Qdrant/embedding/LLM read-only, and a temporary SQLite database
for the auth check (your user database is not touched). With embedded Qdrant (QDRANT_PATH), stop
uvicorn first or use --server: an embedded store can only be opened by one process.

Statuses: PASS, WARN (works, with a caveat), FAIL, BLOCKED (external dependency unavailable).
Nothing is reported as PASS unless it was actually exercised.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import pkgutil
import secrets
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

PASS, WARN, FAIL, BLOCKED = "PASS", "WARN", "FAIL", "BLOCKED"
SPEC_ROUTES = [
    ("What is Article 21?", "simple"),
    ("Explain the difference between Article 14 and Article 21.", "moderate"),
    ("Compare the legal consequences under IPC and BNS, identify the corresponding provisions, analyze how the "
     "change affects an accused person, and cite the relevant authorities.", "complex"),
    ("Will I win my case?", "refuse"),
]


class Verifier:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []
        self.http: httpx.AsyncClient | None = None
        self.token: str | None = None
        self.llm_ok = False
        self.top_hit: dict[str, Any] | None = None

    async def step(self, name: str, fn: Callable[[], Awaitable[tuple[str, str]]]) -> str:
        start = time.perf_counter()
        try:
            status, detail = await fn()
        except Exception as exc:  # report every failure as a row; keep verifying the rest
            status, detail = FAIL, f"{type(exc).__name__}: {str(exc)[:300]}"
        n = len(self.rows) + 1
        self.rows.append((name, status, detail))
        print(f"{n:>2}. {name:<24} {status:<8} {detail} ({(time.perf_counter() - start) * 1000:.0f} ms)", flush=True)
        return status

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def get(self, path: str, **kw: Any) -> httpx.Response:
        assert self.http is not None
        return await self.http.get(path, headers=self.auth_headers(), **kw)

    async def post(self, path: str, body: Any = None, **kw: Any) -> httpx.Response:
        assert self.http is not None
        return await self.http.post(path, json=body, headers=self.auth_headers(), **kw)


# --------------------------------------------------------------------- static checks
async def check_python() -> tuple[str, str]:
    if sys.version_info < (3, 11):  # noqa: UP036 - this script exists to detect old interpreters
        return FAIL, f"Python {sys.version.split()[0]} (3.11+ required)"
    in_venv = sys.prefix != sys.base_prefix
    missing = []
    for mod in ("fastapi", "uvicorn", "langgraph", "qdrant_client", "sentence_transformers", "groq", "sqlalchemy",
                "alembic", "jwt", "bcrypt"):
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        return FAIL, f"missing packages: {missing} (pip install -r requirements.txt)"
    note = "" if in_venv else " — not running inside a virtualenv"
    return (PASS if in_venv else WARN), f"Python {sys.version.split()[0]}{note}"


async def check_config(holder: dict) -> tuple[str, str]:
    from app.core.config import Settings

    settings = Settings()
    holder["settings"] = settings
    store = f"remote {settings.qdrant_url.split('//')[-1].split('/')[0]}" if settings.qdrant_url else f"embedded {settings.qdrant_path}"
    key = "set" if settings.llm_api_key else "NOT set"
    return PASS, (f"env={settings.app_env.value}, qdrant={store}, llm={','.join(f'{p}:{m}' for p, m in settings.llm_targets)} "
                  f"(key {key}), graph={'on' if settings.graph_enabled else 'off'}")


async def check_imports() -> tuple[str, str]:
    import app

    names = [m.name for m in pkgutil.walk_packages(app.__path__, "app.")]
    failed = []
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as exc:  # report, don't stop
            failed.append(f"{name}: {type(exc).__name__}")
    return (FAIL, "; ".join(failed[:5])) if failed else (PASS, f"{len(names)} modules imported")


# --------------------------------------------------------------------- HTTP checks
async def run_http_checks(v: Verifier) -> None:
    async def root() -> tuple[str, str]:
        r = await v.get("/")
        b = r.json()
        return (PASS, f"{b['service']} {b['version']}") if r.status_code == 200 and b["status"] == "ok" else (FAIL, r.text[:200])

    async def health() -> tuple[str, str]:
        r = await v.get("/health")
        return (PASS, "healthy") if r.json() == {"status": "healthy"} else (FAIL, r.text[:200])

    async def readiness() -> tuple[str, str]:
        deadline = time.monotonic() + 240
        while True:
            r = await v.get("/ready")
            body = r.json()
            if r.status_code == 200 or body["checks"].get("embedding") != "loading" or time.monotonic() > deadline:
                break
            await asyncio.sleep(3)  # embedding model loads in the background on first start
        v.llm_ok = body["checks"].get("llm") == "configured"
        checks = ", ".join(f"{k}={s}" for k, s in body["checks"].items())
        if r.status_code == 200:
            return PASS, checks
        external = {"qdrant", "llm", "knowledge_graph"}
        return (BLOCKED if set(body["failed"]) <= external else FAIL), f"failed={body['failed']}: {checks}"

    async def openapi() -> tuple[str, str]:
        r = await v.get("/openapi.json")
        if r.status_code != 200:
            return FAIL, f"/openapi.json -> {r.status_code} (docs disabled in production unless DOCS_ENABLED=true)"
        spec = r.json()
        ops = sum(len(p) for p in spec["paths"].values())
        bearer = any(s.get("scheme") == "bearer" for s in spec["components"].get("securitySchemes", {}).values())
        docs = (await v.get("/docs")).status_code == 200 and (await v.get("/redoc")).status_code == 200
        ok = bearer and docs and ops >= 15
        return (PASS if ok else FAIL), f"{ops} operations, bearer auth={bearer}, /docs+/redoc={docs}"

    async def auth() -> tuple[str, str]:
        user, pw = f"verify_{secrets.token_hex(4)}", secrets.token_urlsafe(16) + "-1a"
        r = await v.post("/api/v1/auth/signup", {"username": user, "password": pw})
        if r.status_code == 403:
            return BLOCKED, "registration disabled (AUTH_ALLOW_REGISTRATION=false)"
        if r.status_code != 201:
            return FAIL, f"signup -> {r.status_code} {r.text[:200]}"
        r = await v.post("/api/v1/auth/login", {"username": user, "password": pw})
        v.token = r.json().get("access_token")
        me = await v.get("/api/v1/auth/me")
        bad = await v.post("/api/v1/auth/login", {"username": user, "password": "wrong-pass-1"})
        ok = r.status_code == 200 and me.status_code == 200 and bad.status_code == 401
        return (PASS if ok else FAIL), f"signup/login/me with signed JWT; wrong password -> {bad.status_code}"

    async def embedding() -> tuple[str, str]:
        r = await v.get("/api/v1/diagnostics/embedding", timeout=300)
        b = r.json()
        if r.status_code == 404:
            return BLOCKED, "diagnostics disabled (DIAGNOSTICS_ENABLED=false)"
        detail = f"{b['model']} dim={b.get('dimension')} norm={b.get('l2_norm')} finite={b.get('finite')}"
        return (PASS if b["ok"] else FAIL), detail + (f" error={b['error']}" if b.get("error") else "")

    async def qdrant() -> tuple[str, str]:
        b = (await v.get("/api/v1/diagnostics/qdrant")).json()
        if not b["reachable"]:
            return BLOCKED, f"{b['mode']} {b['target']} unreachable: {b.get('error')}"
        if not b["collection_exists"] or not b.get("points"):
            return FAIL, f"collection {b['collection']} empty/missing — run: python scripts/ingest.py --source data/legal_docs"
        ok = b["vector_dimension"] == b["expected_dimension"] and b["test_query_ok"]
        return (PASS if ok else FAIL), (f"{b['mode']} {b['collection']}: {b['points']} points, dim {b['vector_dimension']}, "
                                        f"{b['distance']}, sparse={b['sparse_enabled']}, probe query ok={b['test_query_ok']}")

    async def retrieval() -> tuple[str, str]:
        r = await v.post("/api/v1/search", {"query": "punishment", "top_k": 5}, timeout=120)
        if r.status_code != 200:
            return FAIL, f"search -> {r.status_code} {r.text[:200]}"
        b = r.json()
        d = b["diagnostics"]
        if b["results"]:
            v.top_hit = b["results"][0]
        src = {k: s["hits"] for k, s in d["sources"].items() if s["executed"]}
        ok = d["sources"]["dense"]["hits"] > 0 and d["sources"]["sparse"]["hits"] > 0 and d["fusion"]["count"] > 0
        return (PASS if ok else FAIL), f"mode={d['retrieval_mode']} hits={src} fused={d['fusion']['count']} results={b['total']}"

    async def reranker() -> tuple[str, str]:
        r = await v.post("/api/v1/search", {"query": "punishment for murder", "top_k": 5, "profile": "BALANCED"},
                         timeout=300)
        b = r.json()
        rr = b["diagnostics"]["reranking"]
        if not rr["executed"] or not rr["count"]:
            return FAIL, "reranking stage did not run"
        scored = all(res["rerank_score"] is not None for res in b["results"])
        fallback = [w for w in b["warnings"] if "reranker unavailable" in w]
        if fallback:
            return WARN, f"configured reranker failed, fallback used: {fallback[0]}"
        return (PASS if scored else FAIL), f"{rr['method']} reranked {rr['count']} candidates; all results carry rerank scores"

    async def routing() -> tuple[str, str]:
        got = []
        for query, expected in SPEC_ROUTES:
            body = (await v.post("/api/v1/diagnostics/route", {"query": query})).json()
            got.append((expected, body["route"], len(body["subqueries"])))
        ok = all(e == g for e, g, _ in got)
        return (PASS if ok else FAIL), "; ".join(f"{e}->{g}({n} subq)" for e, g, n in got)

    async def langgraph() -> tuple[str, str]:
        search = (await v.post("/api/v1/search", {"query": "Compare IPC 420 and BNS 318 and explain the impact", "top_k": 5})).json()
        d = search["diagnostics"]
        stages_ok = d["route"] == "complex" and len(d["subqueries"]) > 1 and d["fusion"]["executed"] and \
            d["reranking"]["executed"] and d["context"]["executed"] and not d["generation"]["executed"]
        refuse = (await v.post("/api/v1/chat", {"query": "Will I win my case?"})).json()
        refuse_ok = refuse["refused"] and refuse["metadata"]["candidates"] == 0 and refuse["metadata"]["model"] is None
        off = (await v.post("/api/v1/chat", {"query": "What are the rules for space mining royalties on Mars?"})).json()
        off_ok = off["metadata"]["model"] is None  # evidence gate: no LLM call
        ok = stages_ok and refuse_ok and off_ok
        return (PASS if ok else FAIL), (f"complex path stages ok={stages_ok} ({len(d['subqueries'])} subqueries); "
                                        f"safety short-circuit ok={refuse_ok}; evidence gate ok={off_ok}")

    async def llm() -> tuple[str, str]:
        if not v.llm_ok:
            return BLOCKED, "no LLM credentials configured"
        b = (await v.post("/api/v1/diagnostics/llm", {}, timeout=60)).json()
        if not b["ok"]:
            return BLOCKED, f"provider call failed: {b['error']}"
        return PASS, f"{b['provider']}:{b['model']} replied {b['response_preview']!r} in {b['latency_ms']:.0f} ms"

    def question() -> str:
        if v.top_hit:
            md = v.top_hit["metadata"]
            label = f"{md.get('act') or md['title']} {'Section ' + md['section'] if md.get('section') else ''}".strip()
            return f"What does {label} provide? Answer briefly."
        return "What does the indexed law say about punishment?"

    async def chat() -> tuple[str, str]:
        if not v.llm_ok:
            return BLOCKED, "no LLM credentials configured"
        r = await v.post("/api/v1/chat", {"query": question()}, timeout=180)
        if r.status_code in (502, 503):
            return BLOCKED, r.json()["error"]["message"]
        b = r.json()
        m = b["metadata"]
        valid = (m.get("output_validation") or {}).get("valid")
        status = PASS if b["answer"] and b["citations"] and valid else WARN
        return status, (f"route={m['route']} model={m['model']} citations={len(b['citations'])} validated={valid} "
                        f"latency={m['latency_ms']:.0f} ms")

    async def streaming() -> tuple[str, str]:
        if not v.llm_ok:
            return BLOCKED, "no LLM credentials configured"
        assert v.http is not None
        types: list[str] = []
        async with v.http.stream("POST", "/api/v1/chat/stream", json={"query": question()},
                                 headers=v.auth_headers(), timeout=180) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    types.append(json.loads(line[6:])["type"])
        tokens = types.count("token")
        ok = types[:1] == ["start"] and types[-1:] == ["done"] and tokens > 1
        return (PASS if ok else FAIL), f"{len(types)} events, {tokens} token events, last={types[-1] if types else None}"

    for name, fn in (("Root endpoint", root), ("Health", health), ("Readiness", readiness), ("OpenAPI / docs", openapi),
                     ("Authentication", auth), ("Embedding provider", embedding), ("Qdrant", qdrant),
                     ("Hybrid retrieval", retrieval), ("Reranker", reranker), ("Complexity routing", routing),
                     ("LangGraph", langgraph), ("LLM provider", llm), ("Chat", chat), ("Streaming", streaming)):
        await v.step(name, fn)


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--server", help="verify a running server at this base URL instead of starting the app in-process")
    args = p.parse_args()
    line = "=" * 60
    print(f"{line}\nLEGAL LENS BACKEND VERIFICATION\n{line}")
    v = Verifier()
    holder: dict[str, Any] = {}
    await v.step("Python environment", check_python)
    await v.step("Configuration", lambda: check_config(holder))
    await v.step("Application imports", check_imports)

    if args.server:
        async def reachable() -> tuple[str, str]:
            r = await v.get("/health", timeout=5)
            return (PASS, f"server at {args.server} reachable") if r.status_code == 200 else (FAIL, r.text[:200])

        v.http = httpx.AsyncClient(base_url=args.server, timeout=120)
        await v.step("FastAPI startup", reachable)
        await run_http_checks(v)
        await v.http.aclose()
    elif "settings" in holder:
        from asgi_lifespan import LifespanManager

        from app.main import create_app

        tmp_db = Path(tempfile.mkdtemp()) / "verify.db"
        settings = holder["settings"].model_copy(update={"database_url": f"sqlite+aiosqlite:///{tmp_db.as_posix()}",
                                                         "rate_limit_enabled": False, "log_level": "WARNING"})
        app = create_app(settings)
        manager = LifespanManager(app, startup_timeout=120, shutdown_timeout=30)

        async def startup() -> tuple[str, str]:
            await manager.__aenter__()
            errors = app.state.container.startup_errors
            if errors.get("vector_store"):
                hint = " — is uvicorn running with the embedded store? stop it or use --server" if settings.qdrant_path else ""
                return BLOCKED, f"started, but vector store unavailable: {errors['vector_store']}{hint}"
            return PASS, "lifespan startup complete (real container, temporary auth database)"

        if await v.step("FastAPI startup", startup) != FAIL:
            v.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://verify", timeout=300)
            await run_http_checks(v)
            await v.http.aclose()
            await manager.__aexit__(None, None, None)

    statuses = [s for _, s, _ in v.rows]
    final = FAIL if FAIL in statuses else BLOCKED if BLOCKED in statuses else PASS
    print(f"{line}\nFINAL RESULT: {final}   (pass {statuses.count(PASS)}, warn {statuses.count(WARN)}, "
          f"fail {statuses.count(FAIL)}, blocked {statuses.count(BLOCKED)})\n{line}")
    return 0 if final == PASS else 1


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(asyncio.run(main()))
