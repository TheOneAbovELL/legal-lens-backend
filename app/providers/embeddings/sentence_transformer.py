"""SentenceTransformers embedding provider (default: BAAI/bge-m3, 1024-d, multilingual)."""

from __future__ import annotations

import asyncio
import threading
from collections import OrderedDict
from collections.abc import Sequence
from typing import Any

from app.core.exceptions import EmbeddingError
from app.core.logging import get_logger
from app.providers.embeddings.base import EmbeddingProvider, validate_vectors

logger = get_logger(__name__)


class _LRU:
    """Small bounded LRU cache (thread-safe enough for asyncio + to_thread usage)."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._data: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> list[float] | None:
        with self._lock:
            value = self._data.get(key)
            if value is not None:
                self._data.move_to_end(key)
            return value

    def put(self, key: str, value: list[float]) -> None:
        if self.capacity <= 0:
            return
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.capacity:
                self._data.popitem(last=False)


class SentenceTransformerEmbedder(EmbeddingProvider):
    def __init__(
        self,
        model_name: str,
        *,
        dimension: int,
        device: str = "cpu",
        model_version: str = "1",
        batch_size: int = 16,
        query_cache_size: int = 512,
        query_prefix: str = "",
    ) -> None:
        self.model_name = model_name
        self.model_version = model_version
        self.dimension = dimension
        self._device = device
        self._batch_size = batch_size
        self._query_prefix = query_prefix
        self._cache = _LRU(query_cache_size)
        self._model: Any = None
        self._load_lock = threading.Lock()

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is None:
                try:
                    from sentence_transformers import SentenceTransformer

                    model = SentenceTransformer(self.model_name, device=self._device)
                except Exception as exc:  # model download/IO/ImportError
                    raise EmbeddingError(f"failed to load embedding model {self.model_name}: {exc}") from exc
                actual = model.get_sentence_embedding_dimension()
                if actual != self.dimension:
                    raise EmbeddingError(
                        f"model {self.model_name} produces {actual}-d vectors but "
                        f"EMBEDDING_DIMENSION={self.dimension}"
                    )
                self._model = model
                logger.info("embedding model loaded", extra={"model": self.model_name, "dim": actual})
        return self._model

    async def warmup(self) -> None:
        await asyncio.to_thread(self._load)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        try:
            array = model.encode(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise EmbeddingError(f"embedding inference failed: {exc}") from exc
        vectors = [row.tolist() for row in array]
        validate_vectors(vectors, len(texts), self.dimension)
        return vectors

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not t.strip() for t in texts):
            raise EmbeddingError("cannot embed empty text")
        return await asyncio.to_thread(self._encode, list(texts))

    async def embed_query(self, text: str) -> list[float]:
        text = text.strip()
        if not text:
            raise EmbeddingError("cannot embed an empty query")
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        [vector] = await asyncio.to_thread(self._encode, [self._query_prefix + text])
        self._cache.put(text, vector)
        return vector
