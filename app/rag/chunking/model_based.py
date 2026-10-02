"""Model-backed chunking strategies: embedding-based semantic chunking and LLM-driven chunking.

Both are ingestion-time only (never per query) and fall back to deterministic behaviour.
"""

from __future__ import annotations

import json
import math

from app.core.exceptions import LLMProviderError
from app.core.logging import get_logger
from app.domain.documents import LegalUnit, StructuredDocument
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.llm.base import ChatMessage, LLMRequest
from app.providers.llm.router import LLMRouter
from app.rag.chunking.base import ChunkingProfile
from app.rag.chunking.segments import Span, make_span, pack, split_sentences
from app.rag.chunking.strategies import RecursiveChunker

logger = get_logger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    k = (len(ordered) - 1) * pct / 100
    lo, hi = math.floor(k), math.ceil(k)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


class SemanticChunker(RecursiveChunker):
    """Splits where the embedding distance between consecutive sentences spikes.

    params:
      threshold_type: "percentile" (default) | "absolute"
      threshold: percentile (0-100, default 90) or absolute cosine distance (e.g. 0.35)
    Groups larger than ``chunk_size`` are re-packed by sentence; chunks never cross units.
    """

    strategy_name = "semantic"

    def __init__(self, profile: ChunkingProfile, embedder: EmbeddingProvider) -> None:
        super().__init__(profile)
        self._embedder = embedder

    async def split_unit(self, document: StructuredDocument, unit: LegalUnit) -> list[Span]:
        text = document.document.text
        sentences = [s for b in self.block_spans(document, unit) for s in split_sentences(text, b.start, b.end)]
        if len(sentences) <= 2:
            return pack(text, sentences, self.profile.chunk_size, 0)
        vectors = await self._embedder.embed_documents([text[s.start : s.end] for s in sentences])
        distances = [1 - _cosine(vectors[i], vectors[i + 1]) for i in range(len(vectors) - 1)]
        mode = self.profile.params.get("threshold_type", "percentile")
        raw = float(self.profile.params.get("threshold", 90 if mode == "percentile" else 0.35))
        threshold = _percentile(distances, raw) if mode == "percentile" else raw

        groups: list[list[Span]] = [[sentences[0]]]
        boundaries: list[float | None] = [None]
        for i, distance in enumerate(distances):
            if distance > threshold:
                groups.append([])
                boundaries.append(distance)
            groups[-1].append(sentences[i + 1])

        spans: list[Span] = []
        for group, boundary in zip(groups, boundaries, strict=False):
            info = {"semantic_boundary": {
                "method": "embedding_distance", "threshold_type": mode, "threshold": round(threshold, 4),
                "boundary_distance": round(boundary, 4) if boundary is not None else None,
            }}
            for span in pack(text, group, self.profile.chunk_size, self.profile.overlap):
                span.info.update(info)
                spans.append(span)
        return self._merge_small(text, spans)

    def _merge_small(self, text: str, spans: list[Span]) -> list[Span]:
        minimum = self.profile.min_chunk_tokens
        if not minimum:
            return spans
        merged: list[Span] = []
        for span in spans:
            if merged and (span.tokens < minimum or merged[-1].tokens < minimum) and (
                merged[-1].tokens + span.tokens <= self.profile.chunk_size
            ):
                combined = make_span(text, merged[-1].start, span.end, **merged[-1].info)
                if combined:
                    merged[-1] = combined
                    continue
            merged.append(span)
        return merged


_AI_PROMPT = """You segment legal text into retrieval chunks. The text is given as numbered sentences.
Return JSON: {"boundaries": [indices of sentences that START a new chunk, ascending, excluding 0]}.
Rules: keep a provision together with its Explanation/Proviso/Exception when possible; start a new
chunk where the legal topic changes; each chunk should be roughly %(size)d tokens or fewer.
Do not rewrite or summarise the text."""


class AIChunker(RecursiveChunker):
    """LLM-proposed boundaries over numbered sentences (validated); recursive fallback.

    params: max_llm_calls (default 50) bounds ingestion cost per run.
    """

    strategy_name = "ai"

    def __init__(self, profile: ChunkingProfile, llm: LLMRouter) -> None:
        super().__init__(profile)
        self._llm = llm
        self._calls = 0
        self._max_calls = int(profile.params.get("max_llm_calls", 50))

    async def split_unit(self, document: StructuredDocument, unit: LegalUnit) -> list[Span]:
        text = document.document.text
        blocks = self.block_spans(document, unit)
        if sum(b.tokens for b in blocks) <= self.profile.chunk_size or self._calls >= self._max_calls:
            return await super().split_unit(document, unit)
        sentences = [s for b in blocks for s in split_sentences(text, b.start, b.end)]
        numbered = "\n".join(f"[{i}] {text[s.start:s.end]}" for i, s in enumerate(sentences))
        self._calls += 1
        try:
            response = await self._llm.complete(LLMRequest(
                messages=[
                    ChatMessage(role="system", content=_AI_PROMPT % {"size": self.profile.chunk_size}),
                    ChatMessage(role="user", content=numbered),
                ],
                temperature=0.0, max_tokens=300, json_mode=True,
            ))
            boundaries = sorted({int(i) for i in json.loads(response.text).get("boundaries", []) if 0 < int(i) < len(sentences)})
        except (LLMProviderError, ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
            logger.warning("ai chunking fell back to recursive", extra={"unit": unit.unit_id, "error_type": type(exc).__name__})
            return await super().split_unit(document, unit)
        spans: list[Span] = []
        starts = [0, *boundaries]
        for a, b in zip(starts, [*boundaries, len(sentences)], strict=False):
            for span in pack(text, sentences[a:b], self.profile.chunk_size, 0):
                span.info["semantic_boundary"] = {"method": "llm", "model": response.model, "start_sentence": a}
                spans.append(span)
        return spans
