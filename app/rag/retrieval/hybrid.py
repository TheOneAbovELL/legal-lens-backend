"""Hybrid retrieval: concurrent multi-source, multi-sub-query retrieval with weighted RRF fusion.

Per (sub-query, source) result list, each chunk receives ``weight_source * 1 / (k + rank)``,
scaled by the sub-query's priority weight; contributions are summed across lists so chunks that
answer several sub-queries rise. Results are then de-duplicated by chunk ID and by content hash
(the same text indexed under two chunk profiles or document versions).
"""

from __future__ import annotations

import asyncio
import time

from pydantic import BaseModel, Field

from app.core.exceptions import AppError, RetrievalError
from app.core.logging import get_logger
from app.domain.query import LegalEntity, SubQuery
from app.domain.retrieval import RetrievalFilters, RetrievedChunk
from app.rag.retrieval.base import RetrievalQuery, Retriever

logger = get_logger(__name__)

PRIORITY_WEIGHTS = {0: 1.0, 1: 0.85, 2: 0.7, 3: 0.6, 4: 0.5, 5: 0.5}


class SourceError(BaseModel):
    source: str
    subquery_id: str | None
    error: str


class HybridResult(BaseModel):
    candidates: list[RetrievedChunk]
    source_counts: dict[str, int] = Field(default_factory=dict)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    errors: list[SourceError] = Field(default_factory=list)


class HybridRetriever:
    def __init__(self, retrievers: list[Retriever], rrf_k: int = 60) -> None:
        self._retrievers = {r.name: r for r in retrievers}
        self._rrf_k = rrf_k

    @property
    def sources(self) -> list[str]:
        return list(self._retrievers)

    async def _run(
        self, retriever: Retriever, query: RetrievalQuery, filters: RetrievalFilters | None, top_k: int,
        timings: dict[str, float],
    ) -> list[RetrievedChunk]:
        start = time.perf_counter()
        try:
            return await retriever.retrieve(query, filters, top_k)
        finally:
            timings[retriever.name] = timings.get(retriever.name, 0.0) + (time.perf_counter() - start) * 1000

    async def retrieve(
        self,
        subqueries: list[SubQuery],
        entities: list[LegalEntity],
        *,
        filters: RetrievalFilters | None,
        candidate_k: int,
        sources: list[str],
        weights: dict[str, float] | None = None,
    ) -> HybridResult:
        weights = weights or {}
        active = [self._retrievers[s] for s in sources if s in self._retrievers]
        if not active:
            raise RetrievalError("no retrieval sources enabled for this request")

        tasks: list[tuple[Retriever, SubQuery]] = []
        for retriever in active:
            if retriever.per_subquery:
                tasks.extend((retriever, sq) for sq in subqueries)
            else:
                primary = min(subqueries, key=lambda s: s.priority)
                tasks.append((retriever, primary))

        timings: dict[str, float] = {}
        outcomes = await asyncio.gather(
            *[
                self._run(r, RetrievalQuery(text=sq.query, subquery_id=sq.subquery_id, entities=entities),
                          filters, candidate_k, timings)
                for r, sq in tasks
            ],
            return_exceptions=True,
        )

        errors: list[SourceError] = []
        fused: dict[str, RetrievedChunk] = {}
        counts: dict[str, int] = {}
        succeeded = 0
        for (retriever, sq), outcome in zip(tasks, outcomes, strict=False):
            if isinstance(outcome, BaseException):
                if not isinstance(outcome, (AppError, OSError, TimeoutError)):
                    raise outcome  # programming errors must surface, not be swallowed
                logger.warning("retriever failed", extra={"source": retriever.name, "error_type": type(outcome).__name__})
                errors.append(SourceError(source=retriever.name, subquery_id=sq.subquery_id, error=type(outcome).__name__))
                continue
            succeeded += 1
            counts[retriever.name] = counts.get(retriever.name, 0) + len(outcome)
            weight = weights.get(retriever.name, 1.0) * PRIORITY_WEIGHTS.get(sq.priority, 0.5)
            for item in outcome:
                rank = item.ranks[retriever.name]
                contribution = weight / (self._rrf_k + rank)
                existing = fused.get(item.chunk_id)
                if existing is None:
                    item.fused_score = contribution
                    item.subquery_ranks = {sq.subquery_id: rank}
                    fused[item.chunk_id] = item
                    continue
                prev = existing.subquery_ranks.get(sq.subquery_id)
                existing.subquery_ranks[sq.subquery_id] = rank if prev is None else min(prev, rank)
                existing.fused_score += contribution
                for source, score in item.scores.items():
                    existing.scores[source] = max(existing.scores.get(source, score), score)
                for source, r in item.ranks.items():
                    existing.ranks[source] = min(existing.ranks.get(source, r), r)
                for sid in item.subquery_ids:
                    if sid not in existing.subquery_ids:
                        existing.subquery_ids.append(sid)

        if succeeded == 0:
            raise RetrievalError("all retrieval sources failed: " + ", ".join(sorted({e.source for e in errors})))

        by_hash: dict[str, RetrievedChunk] = {}
        for item in sorted(fused.values(), key=lambda c: c.fused_score, reverse=True):
            key = item.metadata.content_hash
            kept = by_hash.get(key)
            if kept is None:
                by_hash[key] = item
            else:  # merge provenance of an identical passage into the higher-scored copy
                for sid in item.subquery_ids:
                    if sid not in kept.subquery_ids:
                        kept.subquery_ids.append(sid)
        candidates = sorted(by_hash.values(), key=lambda c: c.fused_score, reverse=True)
        return HybridResult(
            candidates=candidates,
            source_counts=counts,
            timings_ms={k: round(v, 2) for k, v in timings.items()},
            errors=errors,
        )
