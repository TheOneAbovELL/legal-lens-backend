"""Rerankers: none, lightweight lexical, and cross-encoder (with lexical fallback)."""

from __future__ import annotations

import asyncio
import math
import threading
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from app.core.exceptions import RerankingError
from app.core.logging import get_logger
from app.domain.query import EntityType, LegalEntity
from app.domain.retrieval import RetrievedChunk
from app.rag.sparse import lexical_terms

logger = get_logger(__name__)


class Reranker(ABC):
    name: ClassVar[str]

    @abstractmethod
    async def rerank(
        self, query: str, candidates: list[RetrievedChunk], entities: list[LegalEntity], top_k: int
    ) -> list[RetrievedChunk]:
        """Set ``rerank_score`` and return the best ``top_k`` candidates, best first."""


class NoopReranker(Reranker):
    name = "none"

    async def rerank(self, query, candidates, entities, top_k):  # type: ignore[no-untyped-def]
        return sorted(candidates, key=lambda c: c.fused_score, reverse=True)[:top_k]


def _provision_match(chunk: RetrievedChunk, entities: list[LegalEntity]) -> bool:
    md = chunk.metadata
    return any(
        e.type in (EntityType.SECTION, EntityType.ARTICLE) and md.section == e.value and (e.act is None or md.act == e.act)
        for e in entities
    )


class LexicalReranker(Reranker):
    """Deterministic, model-free: blends normalised fused score, query-term coverage and an
    exact-provision bonus. Cheap enough for the SIMPLE path."""

    name = "lexical"

    def __init__(self, fused_weight: float = 0.5, coverage_weight: float = 0.35, provision_bonus: float = 0.15) -> None:
        self._w_fused = fused_weight
        self._w_cov = coverage_weight
        self._bonus = provision_bonus

    async def rerank(self, query, candidates, entities, top_k):  # type: ignore[no-untyped-def]
        if not candidates:
            return []
        terms = set(lexical_terms(query))
        best = max(c.fused_score for c in candidates) or 1.0
        for c in candidates:
            text_terms = set(lexical_terms(f"{c.context_header} {c.content}"))
            coverage = len(terms & text_terms) / len(terms) if terms else 0.0
            c.rerank_score = round(
                self._w_fused * (c.fused_score / best)
                + self._w_cov * coverage
                + (self._bonus if _provision_match(c, entities) else 0.0),
                6,
            )
        return sorted(candidates, key=lambda c: c.rerank_score or 0.0, reverse=True)[:top_k]


class CrossEncoderReranker(Reranker):
    name = "cross_encoder"

    def __init__(self, model_name: str, device: str = "cpu", max_candidates: int = 50) -> None:
        self.model_name = model_name
        self._device = device
        self._max_candidates = max_candidates
        self._model: Any = None
        self._lock = threading.Lock()

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    def _load(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    try:
                        from sentence_transformers import CrossEncoder

                        self._model = CrossEncoder(self.model_name, device=self._device)
                    except Exception as exc:
                        raise RerankingError(f"failed to load reranker {self.model_name}: {exc}") from exc
        return self._model

    async def warmup(self) -> None:
        await asyncio.to_thread(self._load)

    def _score(self, query: str, texts: list[str]) -> list[float]:
        model = self._load()
        try:
            return [float(s) for s in model.predict([(query, t) for t in texts], show_progress_bar=False)]
        except Exception as exc:
            raise RerankingError(f"cross-encoder inference failed: {exc}") from exc

    async def rerank(self, query, candidates, entities, top_k):  # type: ignore[no-untyped-def]
        pool = sorted(candidates, key=lambda c: c.fused_score, reverse=True)[: self._max_candidates]
        if not pool:
            return []
        scores = await asyncio.to_thread(self._score, query, [f"{c.context_header}\n{c.content}" for c in pool])
        for c, s in zip(pool, scores, strict=False):
            # Logit -> relevance probability, so all rerankers emit comparable [0, 1] scores.
            c.rerank_score = round(1.0 / (1.0 + math.exp(-s)), 6)
        return sorted(pool, key=lambda c: c.rerank_score or 0.0, reverse=True)[:top_k]


class RerankerSet:
    """Dispatches to a named reranker; on failure optionally falls back to the lexical one.

    Stateless per call (returns which reranker was actually used), so it is safe under
    concurrent requests.
    """

    def __init__(self, rerankers: list[Reranker], fallback: str | None = "lexical") -> None:
        self._rerankers = {r.name: r for r in rerankers}
        self._fallback = fallback

    def get(self, name: str) -> Reranker | None:
        return self._rerankers.get(name)

    async def rerank(
        self, name: str, query: str, candidates: list[RetrievedChunk], entities: list[LegalEntity], top_k: int
    ) -> tuple[list[RetrievedChunk], str, str | None]:
        reranker = self._rerankers.get(name)
        if reranker is None:
            raise RerankingError(f"reranker {name!r} is not configured")
        try:
            return await reranker.rerank(query, candidates, entities, top_k), name, None
        except RerankingError as exc:
            fallback = self._rerankers.get(self._fallback) if self._fallback else None
            if fallback is None or fallback is reranker:
                raise
            logger.warning("reranker failed; using fallback", extra={"reranker": name, "error": str(exc)[:200]})
            result = await fallback.rerank(query, candidates, entities, top_k)
            return result, fallback.name, f"{name} reranker unavailable; {fallback.name} reranking used"
