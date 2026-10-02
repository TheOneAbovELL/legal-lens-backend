"""Chunking profile registry and strategy factory."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.exceptions import ConfigurationError
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.llm.router import LLMRouter
from app.rag.chunking.base import ChunkingProfile, ChunkingStrategy
from app.rag.chunking.model_based import AIChunker, SemanticChunker
from app.rag.chunking.strategies import (
    FixedSizeChunker,
    HierarchicalChunker,
    RecursiveChunker,
    SentenceChunker,
    SlidingWindowChunker,
)

_SIMPLE = {cls.strategy_name: cls for cls in (
    FixedSizeChunker, SentenceChunker, RecursiveChunker, SlidingWindowChunker, HierarchicalChunker,
)}
STRATEGIES = sorted([*_SIMPLE, "semantic", "ai"])


def build_chunker(
    profile: ChunkingProfile, *, embedder: EmbeddingProvider | None = None, llm: LLMRouter | None = None
) -> ChunkingStrategy:
    if profile.strategy in _SIMPLE:
        return _SIMPLE[profile.strategy](profile)
    if profile.strategy == "semantic":
        if embedder is None:
            raise ConfigurationError("semantic chunking requires an embedding provider")
        return SemanticChunker(profile, embedder)
    if profile.strategy == "ai":
        if llm is None:
            raise ConfigurationError("AI chunking requires an LLM provider")
        return AIChunker(profile, llm)
    raise ConfigurationError(f"unknown chunking strategy {profile.strategy!r}; available: {STRATEGIES}")


class ChunkingProfileRegistry:
    def __init__(self, profiles: list[ChunkingProfile], default: str) -> None:
        self._profiles = {p.name: p for p in profiles}
        if default not in self._profiles:
            raise ConfigurationError(f"default chunking profile {default!r} is not defined")
        self.default = default

    @classmethod
    def from_file(cls, path: Path, default: str | None = None) -> ChunkingProfileRegistry:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"cannot load chunking profiles from {path}: {exc}") from exc
        profiles = [ChunkingProfile.model_validate(p) for p in data["profiles"]]
        return cls(profiles, default or data["default"])

    def get(self, name: str) -> ChunkingProfile:
        try:
            return self._profiles[name]
        except KeyError as exc:
            raise ConfigurationError(f"unknown chunking profile {name!r}") from exc

    def names(self, strategy: str | None = None) -> list[str]:
        return [n for n, p in self._profiles.items() if strategy is None or p.strategy == strategy]

    @staticmethod
    def adhoc(strategy: str, chunk_size: int, overlap: int, **params: object) -> ChunkingProfile:
        name = f"{strategy}-{chunk_size}-{overlap}" if overlap else f"{strategy}-{chunk_size}"
        return ChunkingProfile(name=name, strategy=strategy, chunk_size=chunk_size, overlap=overlap, params=dict(params))
