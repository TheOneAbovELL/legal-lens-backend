"""SentenceTransformerEmbedder behaviour with an injected fake model (no download)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.core.exceptions import EmbeddingError
from app.providers.embeddings.sentence_transformer import SentenceTransformerEmbedder


class _FakeModel:
    def __init__(self, dim: int, output: str = "ok") -> None:
        self.dim, self.output, self.calls, self.normalize_flags = dim, output, 0, []

    def get_sentence_embedding_dimension(self) -> int:
        return self.dim

    def encode(self, texts, batch_size, normalize_embeddings, convert_to_numpy, show_progress_bar):  # type: ignore[no-untyped-def]
        self.calls += 1
        self.normalize_flags.append(normalize_embeddings)
        if self.output == "zeros":
            return np.zeros((len(texts), self.dim))
        if self.output == "nan":
            return np.full((len(texts), self.dim), np.nan)
        if self.output == "raise":
            raise RuntimeError("CUDA out of memory")
        rng = np.random.default_rng(len(texts))
        vectors = rng.normal(size=(len(texts), self.dim))
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def embedder(output: str = "ok", dim: int = 8) -> tuple[SentenceTransformerEmbedder, _FakeModel]:
    e = SentenceTransformerEmbedder("fake/model", dimension=dim, query_cache_size=4)
    model = _FakeModel(dim, output)
    e._model = model
    return e, model


async def test_embeds_normalized_finite_vectors_and_caches_queries() -> None:
    e, model = embedder()
    v = await e.embed_query("Section 420 IPC")
    assert len(v) == 8 and all(math.isfinite(x) for x in v)
    assert abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 1e-6
    assert model.normalize_flags == [True]  # normalization requested from the model
    await e.embed_query("Section 420 IPC")
    assert model.calls == 1  # cached
    docs = await e.embed_documents(["a", "b", "c"])
    assert len(docs) == 3


@pytest.mark.parametrize("output", ["zeros", "nan", "raise"])
async def test_failures_raise_instead_of_returning_placeholder_vectors(output: str) -> None:
    e, _ = embedder(output)
    with pytest.raises(EmbeddingError):
        await e.embed_query("x")


async def test_rejects_empty_text() -> None:
    e, _ = embedder()
    with pytest.raises(EmbeddingError):
        await e.embed_query("   ")
    with pytest.raises(EmbeddingError):
        await e.embed_documents(["ok", ""])


async def test_dimension_mismatch_detected_on_load(monkeypatch: pytest.MonkeyPatch) -> None:
    import sentence_transformers

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", lambda *a, **k: _FakeModel(16))
    e = SentenceTransformerEmbedder("fake/model", dimension=8)
    with pytest.raises(EmbeddingError, match="16-d"):
        await e.warmup()
