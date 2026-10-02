"""The previous backend's collection (unnamed 1024-d vector, payload {"text": ...}) stays readable."""

from __future__ import annotations

from qdrant_client import models

from app.domain.retrieval import RetrievalFilters
from app.providers.vector_store.qdrant_store import QdrantVectorStore
from app.rag.retrieval.base import RetrievalQuery
from app.rag.retrieval.retrievers import DenseRetriever
from tests.fakes import HashingEmbedder


async def test_legacy_unnamed_vector_collection_is_readable() -> None:
    embedder = HashingEmbedder(64)
    store = QdrantVectorStore(collection="legal-lens-qdrant", path=":memory:", dense_vector_name="",
                              sparse_vector_name="", allow_create=False)
    client = store._client
    await client.create_collection("legal-lens-qdrant",
                                   vectors_config=models.VectorParams(size=64, distance=models.Distance.COSINE))
    text = "Article 21 guarantees the right to life and personal liberty."
    await client.upsert("legal-lens-qdrant", points=[
        models.PointStruct(id=1, vector=await embedder.embed_query(text), payload={"text": text})])
    await store.ensure_collection(64)  # validates instead of creating
    assert store.sparse_enabled is False
    hits = await DenseRetriever(embedder, store).retrieve(RetrievalQuery(text="right to life"), RetrievalFilters(), 3)
    assert hits and hits[0].content == text and hits[0].metadata.chunk_profile == "external"
    await store.close()


async def test_locked_embedded_store_reports_clear_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.core.exceptions import VectorStoreError

    path = str(tmp_path / "qdrant")
    owner = QdrantVectorStore(collection="c", path=path)  # first process holds the lock
    second = QdrantVectorStore(collection="c", path=path)  # must not crash at construction
    try:
        with __import__("pytest").raises(VectorStoreError, match="in use by another process"):
            await second.ensure_collection(8)
        info = await owner.health()
        assert info["mode"] == "local"
    finally:
        await second.close()
        await owner.close()


async def test_locked_embedded_store_recovers_when_released(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = str(tmp_path / "qdrant")
    owner = QdrantVectorStore(collection="c", path=path)
    second = QdrantVectorStore(collection="c", path=path)
    await owner.close()  # lock released
    await second.ensure_collection(8)  # reopens and works without a restart
    assert (await second.health())["exists"]
    await second.close()
