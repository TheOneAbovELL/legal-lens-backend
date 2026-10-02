"""Diagnostics endpoints and retrieval diagnostics in chat/search responses."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager

from app.container import Container
from app.core.config import Settings
from app.main import create_app
from tests.conftest import ingest_corpus, make_container, make_settings


async def test_config_summary_has_no_secrets(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/diagnostics/config")
    body = resp.json()
    assert resp.status_code == 200 and body["llm_api_key_configured"] is True
    settings = client.container.settings  # type: ignore[attr-defined]
    assert settings.llm_api_key.get_secret_value() not in resp.text
    assert settings.jwt_secret() not in resp.text


async def test_qdrant_diagnostics(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/diagnostics/qdrant")).json()
    assert body["reachable"] and body["collection_exists"] and body["points"] > 0
    assert body["vector_dimension"] == body["expected_dimension"] and body["distance"] == "Cosine"
    assert body["sparse_enabled"] and body["test_query_ok"] and body["test_query_hits"] > 0
    assert body["indexed_chunk_profiles"] == ["hierarchical-400"] and body["error"] is None


async def test_embedding_diagnostics(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/diagnostics/embedding")).json()
    assert body["ok"] and body["finite"] and body["non_zero"] and body["normalized"]
    assert body["dimension"] == body["expected_dimension"] and abs(body["l2_norm"] - 1.0) < 1e-3


async def test_llm_diagnostics(client: httpx.AsyncClient) -> None:
    body = (await client.post("/api/v1/diagnostics/llm", json={})).json()
    assert body["ok"] and body["provider"] == "fake" and body["response_preview"]


@pytest.mark.parametrize(
    ("query", "route", "complexity"),
    [
        ("What is Article 21?", "simple", "SIMPLE"),
        ("Explain the difference between Article 14 and Article 21.", "moderate", "MODERATE"),
        ("Compare the legal consequences under IPC and BNS, identify the corresponding provisions, analyze how the "
         "change affects an accused person, and cite the relevant authorities.", "complex", "COMPLEX"),
        ("Will I win my case?", "refuse", None),
    ],
)
async def test_route_diagnostics(client: httpx.AsyncClient, query: str, route: str, complexity: str | None) -> None:
    body = (await client.post("/api/v1/diagnostics/route", json={"query": query})).json()
    assert body["route"] == route
    if complexity:
        assert body["complexity"]["complexity"] == complexity and body["complexity"]["reasons"]
        assert body["subqueries"] and body["subqueries"][0]["query"]
    if route == "complex":
        assert body["decomposition_method"] == "rule" and len(body["subqueries"]) > 1
        assert all({"subquery_id", "query", "purpose"} <= set(s) for s in body["subqueries"])
    if route == "refuse":
        assert body["would_refuse"] and body["subqueries"] == []


async def test_search_diagnostics_prove_hybrid_execution(client: httpx.AsyncClient) -> None:
    body = (await client.post("/api/v1/search", json={"query": "Section 302 IPC", "top_k": 5})).json()
    d = body["diagnostics"]
    assert d["retrieval_mode"] == "hybrid"
    for source in ("dense", "sparse", "metadata"):
        assert d["sources"][source]["executed"] and d["sources"][source]["hits"] > 0, source
    assert d["sources"]["graph"]["executed"] is False
    assert d["fusion"]["executed"] and d["fusion"]["count"] > 0
    assert d["reranking"]["executed"] and d["reranking"]["method"] == "lexical"
    assert d["context"]["selected_chunks"] == body["total"]
    assert d["generation"]["executed"] is False  # search mode never calls the LLM
    assert d["latency_ms"]["total"] > 0


async def test_chat_diagnostics_include_generation(client: httpx.AsyncClient) -> None:
    body = (await client.post("/api/v1/chat", json={"query": "What is the punishment under Section 420 IPC?"})).json()
    d = body["diagnostics"]
    assert d["generation"]["executed"] and d["generation"]["method"] == "fake:fake-model"
    assert d["provision_mapping"]["count"] >= 1 and d["context"]["selected_chunks"] > 0


async def test_production_disables_diagnostics_and_docs(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, app_env="production", jwt_secret_key="p" * 40, rate_limit_enabled=False)

    def factory(s: Settings) -> Container:
        return make_container(s)

    app = create_app(settings, container_factory=factory)
    async with LifespanManager(app):
        await ingest_corpus(app.state.container)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            assert (await c.get("/docs")).status_code == 404
            assert (await c.get("/openapi.json")).status_code == 404
            assert (await c.get("/api/v1/diagnostics/config")).status_code == 404
            body = (await c.post("/api/v1/chat", json={"query": "What is the punishment for theft?"})).json()
            assert body["diagnostics"] is None and body["metadata"]["subqueries"] == []
            assert body["metadata"]["timings_ms"] == {}
            assert (await c.get("/health")).json() == {"status": "healthy"}
