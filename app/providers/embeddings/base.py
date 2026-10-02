"""Embedding provider interface."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.core.exceptions import EmbeddingError


class EmbeddingProvider(ABC):
    """Converts text into dense vectors. Implementations must never return placeholder vectors."""

    model_name: str
    model_version: str
    dimension: int

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]: ...

    @abstractmethod
    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    @abstractmethod
    async def warmup(self) -> None:
        """Load model weights eagerly (called at application start-up)."""

    @property
    @abstractmethod
    def is_ready(self) -> bool: ...


def validate_vectors(vectors: Sequence[Sequence[float]], expected: int, dimension: int) -> None:
    """Reject wrong counts, wrong dimensions, NaNs and all-zero vectors."""
    if len(vectors) != expected:
        raise EmbeddingError(f"embedding count mismatch: expected {expected}, got {len(vectors)}")
    for vector in vectors:
        if len(vector) != dimension:
            raise EmbeddingError(f"embedding dimension mismatch: expected {dimension}, got {len(vector)}")
        norm_sq = 0.0
        for value in vector:
            if not math.isfinite(value):
                raise EmbeddingError("embedding contains non-finite values")
            norm_sq += value * value
        if norm_sq == 0.0:
            raise EmbeddingError("embedding is an all-zero vector")
