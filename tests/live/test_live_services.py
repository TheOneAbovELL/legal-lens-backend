"""Live-service tests. Skipped unless explicitly enabled:

    LIVE_TESTS=1   -> real LLM provider (uses LLM_API_KEY/GROQ_API_KEY from the environment/.env)
                      and the configured Qdrant (read-only checks)
    MODEL_TESTS=1  -> loads the real embedding model (downloads ~2.3 GB on first use)

These never write to the configured Qdrant collection.
"""

from __future__ import annotations

import math
import os

import pytest

from app.core.config import Settings

live = pytest.mark.skipif(os.getenv("LIVE_TESTS") != "1", reason="set LIVE_TESTS=1 to run live-service tests")
model = pytest.mark.skipif(os.getenv("MODEL_TESTS") != "1", reason="set MODEL_TESTS=1 to load the real embedding model")


def real_settings() -> Settings:
    # Reads .env + environment (the conftest clears env vars, so restore from the live snapshot).
    from tests.conftest import LIVE_ENV

    os.environ.update(LIVE_ENV)
    try:
        return Settings()
    finally:
        for key in LIVE_ENV:
            os.environ.pop(key, None)


@live
async def test_live_llm_minimal_request() -> None:
    from app.providers.llm.base import ChatMessage, LLMRequest
    from app.providers.llm.factory import build_llm_router

    router = build_llm_router(real_settings())
    if not router.configured:
        pytest.skip("no LLM credentials configured")
    try:
        response = await router.complete(LLMRequest(messages=[ChatMessage(role="user", content="Respond with OK.")],
                                                    max_tokens=64, temperature=0.0, timeout=20))
    finally:
        await router.aclose()
    assert response.text.strip() and response.provider


@live
async def test_live_llm_streams_real_deltas() -> None:
    from app.providers.llm.base import ChatMessage, LLMRequest
    from app.providers.llm.factory import build_llm_router
    from app.providers.llm.router import StreamOrigin

    router = build_llm_router(real_settings())
    if not router.configured:
        pytest.skip("no LLM credentials configured")
    try:
        chunks = [c async for c in router.stream(LLMRequest(
            messages=[ChatMessage(role="user", content="Count from 1 to 10 separated by spaces.")], max_tokens=200))]
    finally:
        await router.aclose()
    assert isinstance(chunks[0], StreamOrigin)
    assert sum(1 for c in chunks if c.delta) > 1  # several provider deltas, not one blob


@live
async def test_live_qdrant_read_only() -> None:
    from app.container import build_store

    settings = real_settings()
    store = build_store(settings)
    try:
        info = await store.describe_collection()
    finally:
        await store.close()
    assert "exists" in info
    if info["exists"]:
        assert info["dimension"] == settings.embedding_dimension


@model
async def test_real_embedding_model() -> None:
    from app.container import build_embedder

    e = build_embedder(real_settings())
    v = await e.embed_query("Article 21 protects life and personal liberty.")
    assert len(v) == e.dimension and all(math.isfinite(x) for x in v)
    assert abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 1e-3
    a, b, c = await e.embed_documents(["punishment for theft", "penalty for stealing property", "freedom of speech"])
    cos = lambda x, y: sum(i * j for i, j in zip(x, y, strict=True))  # noqa: E731 - vectors are normalized
    assert cos(a, b) > cos(a, c)  # semantic similarity is meaningful
