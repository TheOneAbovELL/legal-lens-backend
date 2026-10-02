"""HTTP-level tests through the real FastAPI app (lifespan, middleware, DI, error handlers)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager

from app.container import Container
from app.core.config import Settings
from app.main import create_app
from tests.conftest import ingest_corpus, make_container, make_settings
from tests.fakes import ScriptedLLM


async def test_health_and_root(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health")).json() == {"status": "healthy"}
    root = (await client.get("/")).json()
    assert root["status"] == "ok" and root["service"] == "legal-lens-backend" and root["version"]


async def test_readiness_reports_dependencies(client: httpx.AsyncClient) -> None:
    resp = await client.get("/ready")
    body = resp.json()
    assert resp.status_code == 200 and body["status"] == "ready" and body["failed"] == []
    assert body["checks"] == {"application": "ok", "embedding": "ok", "qdrant": "ok", "database": "ok",
                              "llm": "configured", "knowledge_graph": "disabled"}
    qdrant = next(c for c in body["components"] if c["name"] == "qdrant")
    assert qdrant["detail"]["points"] > 0


async def test_readiness_fails_without_llm_credentials(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    def factory(s: Settings) -> Container:
        return make_container(s, ScriptedLLM(configured=False))

    app = create_app(settings, container_factory=factory)
    async with LifespanManager(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/ready")
            body = resp.json()
            assert resp.status_code == 503 and body["status"] == "not_ready"
            assert body["checks"]["llm"] == "not_configured" and body["failed"] == ["llm"]
            assert (await c.get("/health")).status_code == 200  # liveness independent of deps


async def test_chat_json_contract(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/chat", json={"query": "What is the punishment under Section 420 IPC?"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"] and body["source"] == "qdrant"  # legacy fields preserved
    assert body["citations"][0]["section"] == "420"
    alert = next(a for a in body["bns_alerts"] if a["old"] == "IPC 420")
    assert alert["new"] == "BNS 318(4)" and alert["effective"] == "2024-07-01"
    meta = body["metadata"]
    assert meta["route"] == "simple" and meta["retrieval_profile"] == "FAST" and meta["provider"] == "fake"
    assert resp.headers["x-request-id"] == body["request_id"] == meta["request_id"]


async def test_chat_legacy_trailing_slash(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/chat/", json={"query": "What is the punishment for theft?"})
    assert resp.status_code == 200 and "answer" in resp.json()


async def test_chat_sse_stream(client: httpx.AsyncClient) -> None:
    async with client.stream("POST", "/api/v1/chat", json={"query": "Explain Section 420 IPC", "stream": True}) as resp:
        assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/event-stream")
        events = [json.loads(line[6:]) async for line in resp.aiter_lines() if line.startswith("data: ")]
    types = [e["type"] for e in events]
    assert types[0] == "start" and types[-1] == "complete" and types.count("token") > 3
    assert "citation" in types


async def test_chat_stream_endpoint_and_accept_header(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/chat/stream", json={"query": "Explain Section 420 IPC"})
    assert '"type": "complete"' in resp.text
    resp = await client.post("/api/v1/chat", json={"query": "Explain Section 420 IPC"},
                             headers={"Accept": "text/event-stream"})
    assert resp.headers["content-type"].startswith("text/event-stream")


async def test_legacy_plain_text_stream(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/query/stream", json={"query": "Explain Section 420 IPC"})
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/plain")
    assert "cheating" in resp.text and "data:" not in resp.text


async def test_refusal_via_api(client: httpx.AsyncClient) -> None:
    body = (await client.post("/api/v1/chat", json={"query": "Will I win my case?"})).json()
    assert body["refused"] is True and body["citations"] == [] and body["source"] == "none"


async def test_search_structured_results_without_llm(client: httpx.AsyncClient) -> None:
    llm = client.container.llm.providers[0]  # type: ignore[attr-defined]
    before = len(llm.requests)
    resp = await client.post("/api/v1/search", json={"query": "Section 420 IPC cheating", "top_k": 3})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"] is None and len(llm.requests) == before
    assert 0 < body["total"] <= 3 and body["results"][0]["metadata"]["section"] == "420"
    first = body["results"][0]
    assert first["citation"]["chunk_id"] == first["chunk_id"] and first["snippet"]
    assert first["bns_alert"]["new"] == "BNS 318(4)"
    assert body["retrieval_metadata"]["strategy"] and body["processing_time_ms"] > 0


async def test_search_legacy_query_param_and_get(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/v1/search?query=theft")).status_code == 200
    resp = await client.get("/api/v1/search", params={"query": "theft", "top_k": 2})
    assert resp.status_code == 200 and resp.json()["total"] <= 2


async def test_search_filters(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/search", json={"query": "punishment", "filters": {"acts": ["BNS"]}})
    assert resp.json()["results"] and all(r["metadata"]["act"] == "BNS" for r in resp.json()["results"])


async def test_statute_map(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/statute/map", params={"code": "IPC", "section": "304A"})).json()
    assert body["new"] == "BNS 106(1)" and body["mapping_type"] == "exact"
    unknown = (await client.get("/api/v1/statute/map", params={"code": "IPC", "section": "9999"})).json()
    assert unknown["mapping_type"] == "unknown" and unknown["new"] is None
    bad = await client.get("/api/v1/statute/map", params={"code": "XYZ", "section": "1"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_query"


async def test_validation_errors_are_structured(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/chat", json={"query": ""})
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "validation_error"
    resp = await client.post("/api/v1/chat", json={"query": "x", "profile": "TURBO"})
    assert resp.status_code == 422


async def test_request_body_size_limit(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/chat", content=b'{"query": "' + b"a" * 70_000 + b'"}',
                             headers={"content-type": "application/json"})
    assert resp.status_code == 413 and resp.json()["error"]["code"] == "payload_too_large"


async def test_auth_signup_login_me_flow(client: httpx.AsyncClient) -> None:
    signup = await client.post("/api/v1/auth/signup", json={"username": "anjali", "password": "s3cure-pass",
                                                              "role": "advocate", "email": "a@example.com"})
    assert signup.status_code == 201, signup.text
    assert signup.json()["role"] == "advocate" and signup.json()["access_token"]
    dup = await client.post("/api/v1/auth/signup", json={"username": "anjali", "password": "s3cure-pass"})
    assert dup.status_code == 409
    bad = await client.post("/api/v1/auth/login", json={"username": "anjali", "password": "wrong-pass"})
    assert bad.status_code == 401 and bad.headers["www-authenticate"] == "Bearer"
    login = await client.post("/api/v1/auth/login", json={"username": "A@example.com", "password": "s3cure-pass"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["username"] == "anjali" and "password_hash" not in me.json()
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})).status_code == 401


async def test_weak_password_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/signup", json={"username": "bob", "password": "12345678"})
    assert resp.status_code == 422


@pytest.fixture
async def strict_client(tmp_path: Path):  # type: ignore[no-untyped-def]
    settings = make_settings(tmp_path, auth_required=True, rate_limit_enabled=True, rate_limit_requests=3,
                             auth_allow_registration=False)
    holder: dict[str, Container] = {}

    def factory(s: Settings) -> Container:
        holder["c"] = make_container(s)
        return holder["c"]

    app = create_app(settings, container_factory=factory)
    async with LifespanManager(app):
        await ingest_corpus(holder["c"])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            yield c


async def test_auth_required_and_registration_disabled(strict_client: httpx.AsyncClient) -> None:
    resp = await strict_client.post("/api/v1/chat", json={"query": "theft"})
    assert resp.status_code == 401
    signup = await strict_client.post("/api/v1/auth/signup", json={"username": "x_user", "password": "abc12345!"})
    assert signup.status_code == 403


async def test_rate_limit(strict_client: httpx.AsyncClient) -> None:
    statuses = [(await strict_client.post("/api/v1/auth/login", json={"username": "u", "password": "p"})).status_code
                for _ in range(5)]
    assert statuses[:3] == [401, 401, 401] and statuses[3] == 429
    resp = await strict_client.post("/api/v1/auth/login", json={"username": "u", "password": "p"})
    assert resp.headers.get("retry-after")


async def test_session_memory_via_api(client: httpx.AsyncClient) -> None:
    await client.post("/api/v1/chat", json={"query": "Explain Section 420 IPC", "session_id": "abc"})
    body = (await client.post("/api/v1/chat", json={"query": "What is its punishment?", "session_id": "abc"})).json()
    assert body["metadata"]["follow_up"] is True


async def test_internal_errors_do_not_leak(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    class Exploding(ScriptedLLM):
        async def stream(self, request):  # type: ignore[no-untyped-def]
            raise RuntimeError("secret internal detail")
            yield  # pragma: no cover

    def factory(s: Settings) -> Container:
        return make_container(s, Exploding())

    app = create_app(settings, container_factory=factory)
    async with LifespanManager(app):
        await ingest_corpus(app.state.container)
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.post("/api/v1/chat", json={"query": "Explain Section 420 IPC"})
            assert resp.status_code == 500
            assert "secret internal detail" not in resp.text and resp.json()["error"]["code"] == "internal_error"
