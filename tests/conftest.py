"""Shared fixtures: a real Container wired to in-memory Qdrant, a temp SQLite DB and fakes for
the embedding model and LLM. No network, no credentials, no model downloads."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from app.container import Container
from app.core.config import PROJECT_ROOT, Settings
from app.main import create_app
from app.providers.llm.router import LLMRouter
from app.providers.vector_store.qdrant_store import QdrantVectorStore
from app.rag.reranking import LexicalReranker
from tests.fakes import HashingEmbedder, ScriptedLLM

# Determinism: shell variables such as QDRANT_URL or AUTH_REQUIRED must never leak into tests.
# They are removed from this process and kept only for the opt-in live tests (tests/live).
_SETTING_ENV_NAMES = {name.upper() for name in Settings.model_fields} | {"GROQ_API_KEY", "LLM_API_KEY", "ENV"}
LIVE_ENV = {key: os.environ.pop(key) for key in list(os.environ) if key.upper() in _SETTING_ENV_NAMES}

CORPUS = PROJECT_ROOT / "evaluation" / "corpus"
DIM = 64


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "log_json": False,
        "log_level": "WARNING",
        "database_url": f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        "qdrant_url": None,
        "qdrant_path": ":memory:",
        "qdrant_collection": "test-chunks",
        "embedding_dimension": DIM,
        "embedding_preload": False,
        "neo4j_enabled": False,
        "llm_api_key": "test-key",
        "llm_backoff": 0.0,
        "rate_limit_enabled": False,
        "jwt_secret_key": "test-secret-key-that-is-long-enough-1234",
        "evaluation_results_path": tmp_path / "missing.json",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def make_container(settings: Settings, llm: ScriptedLLM | None = None, embedder: HashingEmbedder | None = None) -> Container:
    store = QdrantVectorStore(collection=settings.qdrant_collection, path=":memory:")
    # The cross-encoder slot gets a deterministic stand-in so tests never download models.
    stand_in = LexicalReranker()
    stand_in.name = "cross_encoder"  # type: ignore[misc]
    return Container(
        settings,
        embedder=embedder or HashingEmbedder(DIM),
        store=store,
        llm=LLMRouter([llm or ScriptedLLM()], max_retries=1, backoff=0.0),
        neo4j=None,
        cross_encoder=stand_in,
    )


async def ingest_corpus(container: Container, profile: str = "hierarchical-400") -> None:
    reg = container.chunk_profiles
    for path in sorted(CORPUS.glob("*.txt")):
        report = await container.ingestion.ingest_document(path, CORPUS, reg.get(profile))
        assert report.status == "indexed", report
    await container.refresh_index_state()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM(["Section 420 IPC punishes cheating with imprisonment up to seven years and fine [C1]."])


@pytest_asyncio.fixture
async def container(settings: Settings, llm: ScriptedLLM) -> AsyncIterator[Container]:
    c = make_container(settings, llm)
    await c.startup()
    await ingest_corpus(c)
    yield c
    await c.shutdown()


@pytest_asyncio.fixture
async def client(settings: Settings, llm: ScriptedLLM) -> AsyncIterator[httpx.AsyncClient]:
    holder: dict[str, Container] = {}

    def factory(s: Settings) -> Container:
        holder["c"] = make_container(s, llm)
        return holder["c"]

    app = create_app(settings, container_factory=factory)
    async with LifespanManager(app):
        await ingest_corpus(holder["c"])
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            http.container = holder["c"]  # type: ignore[attr-defined]
            yield http
