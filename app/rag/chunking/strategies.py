"""Deterministic (model-free) chunking strategies.

All of them operate inside one legal unit at a time, so chunk boundaries never cross a
Section / Article / judgment-paragraph boundary.
"""

from __future__ import annotations

import re

from app.core.text import sha256, token_spans
from app.domain.chunks import Chunk, make_chunk_id
from app.domain.documents import LegalUnit, StructuredDocument, UnitKind
from app.rag.chunking.base import ChunkingStrategy
from app.rag.chunking.segments import Span, make_span, pack, split_by_tokens, split_sentences


class FixedSizeChunker(ChunkingStrategy):
    """Baseline: fixed token windows with overlap (ignores sentence/block boundaries).

    ``params.respect_structure`` (default true) still keeps windows inside a legal unit.
    """

    strategy_name = "fixed"

    async def split_unit(self, document: StructuredDocument, unit: LegalUnit) -> list[Span]:
        text = document.document.text
        tokens = [Span(unit.start + s, unit.start + e, 1) for s, e in token_spans(text[unit.start : unit.end])]
        size, overlap = self.profile.chunk_size, self.profile.overlap
        step = max(1, size - overlap)
        spans: list[Span] = []
        for i in range(0, len(tokens), step):
            window = tokens[i : i + size]
            span = make_span(text, window[0].start, window[-1].end)
            if span:
                spans.append(span)
            if i + size >= len(tokens):
                break
        return spans

    async def chunk(self, document: StructuredDocument) -> list[Chunk]:
        if self.profile.params.get("respect_structure", True):
            return await super().chunk(document)
        # Naive baseline: treat the whole document as a single unit.
        whole = LegalUnit(unit_id="document", kind=UnitKind.BODY, start=0, end=len(document.document.text))
        flat = document.model_copy(update={"units": [whole]})
        return await super().chunk(flat)


class SentenceChunker(ChunkingStrategy):
    """Packs whole sentences (legal-abbreviation aware) up to ``chunk_size`` tokens."""

    strategy_name = "sentence"

    async def split_unit(self, document: StructuredDocument, unit: LegalUnit) -> list[Span]:
        text = document.document.text
        sentences = [s for block in self.block_spans(document, unit) for s in split_sentences(text, block.start, block.end)]
        return pack(text, sentences, self.profile.chunk_size, self.profile.overlap, self.profile.min_chunk_tokens)


_RECURSIVE_SEPARATORS = (re.compile(r"\n\s*\n"), re.compile(r"\n"), None, re.compile(r"(?<=;)\s+"), re.compile(r"(?<=,)\s+"))


class RecursiveChunker(ChunkingStrategy):
    """Recursive splitting: legal blocks → paragraphs → lines → sentences → clauses → tokens,
    then adjacent pieces are packed back together up to ``chunk_size``."""

    strategy_name = "recursive"

    def _split(self, text: str, span: Span, level: int, max_tokens: int) -> list[Span]:
        if span.tokens <= max_tokens:
            return [span]
        if level >= len(_RECURSIVE_SEPARATORS):
            return split_by_tokens(text, span.start, span.end, max_tokens)
        separator = _RECURSIVE_SEPARATORS[level]
        if separator is None:
            pieces = split_sentences(text, span.start, span.end)
        else:
            pieces, prev = [], span.start
            for m in separator.finditer(text, span.start, span.end):
                if (p := make_span(text, prev, m.start())) is not None:
                    pieces.append(p)
                prev = m.end()
            if (p := make_span(text, prev, span.end)) is not None:
                pieces.append(p)
        if len(pieces) <= 1:
            return self._split(text, span, level + 1, max_tokens)
        return [sub for piece in pieces for sub in self._split(text, piece, level + 1, max_tokens)]

    def split_span(self, text: str, spans: list[Span], max_tokens: int, overlap: int) -> list[Span]:
        pieces = [p for span in spans for p in self._split(text, span, 0, max_tokens)]
        return pack(text, pieces, max_tokens, overlap, self.profile.min_chunk_tokens)

    async def split_unit(self, document: StructuredDocument, unit: LegalUnit) -> list[Span]:
        text = document.document.text
        return self.split_span(text, self.block_spans(document, unit), self.profile.chunk_size, self.profile.overlap)


class SlidingWindowChunker(ChunkingStrategy):
    """Windows of ``params.window`` sentences advancing by ``params.stride`` sentences."""

    strategy_name = "sliding_window"

    async def split_unit(self, document: StructuredDocument, unit: LegalUnit) -> list[Span]:
        text = document.document.text
        window = int(self.profile.params.get("window", 5))
        stride = int(self.profile.params.get("stride", 3))
        if window < 1 or stride < 1:
            raise ValueError("sliding window requires window >= 1 and stride >= 1")
        sentences = [s for block in self.block_spans(document, unit) for s in split_sentences(text, block.start, block.end)]
        spans: list[Span] = []
        for i in range(0, max(1, len(sentences)), stride):
            group = sentences[i : i + window]
            if not group:
                break
            # Respect the token ceiling by trimming the window, never by cutting a sentence.
            while len(group) > 1 and sum(s.tokens for s in group) > self.profile.chunk_size:
                group = group[:-1]
            if group[0].tokens > self.profile.chunk_size:
                spans.extend(split_by_tokens(text, group[0].start, group[0].end, self.profile.chunk_size))
            elif (span := make_span(text, group[0].start, group[-1].end)) is not None:
                spans.append(span)
            if i + window >= len(sentences):
                break
        return spans


class HierarchicalChunker(RecursiveChunker):
    """Parent/child chunks: a parent per legal unit (or block group when the unit is very long)
    at ``hierarchy_level`` 0, and recursive children at level 1 linked via ``parent_chunk_id``.

    Retrieval can match precise children while context fusion can collapse siblings into the
    parent, keeping a provision's text together.
    """

    strategy_name = "hierarchical"

    async def split_unit(self, document: StructuredDocument, unit: LegalUnit) -> list[Span]:
        text = document.document.text
        doc = document.document
        parent_max = int(self.profile.params.get("parent_max_tokens", 1500))
        blocks = self.block_spans(document, unit)
        parents = pack(text, blocks, parent_max) if sum(b.tokens for b in blocks) > parent_max else [
            s for s in [make_span(text, unit.start, unit.end)] if s
        ]
        spans: list[Span] = []
        for p_index, parent in enumerate(parents):
            children = self.split_span(
                text, [b for b in blocks if b.start < parent.end and b.end > parent.start] or [parent],
                self.profile.chunk_size, self.profile.overlap,
            )
            if len(children) <= 1:
                parent.info["level"] = 1  # a single leaf: no separate parent needed
                spans.append(parent)
                continue
            parent_id = make_chunk_id(
                doc.document_id, doc.version, self.profile.name, f"parent:{unit.unit_id}:{p_index}",
                sha256(text[parent.start : parent.end]),
            )
            parent.info.update(level=0, chunk_id=parent_id)
            spans.append(parent)
            for child in children:
                child.info.update(level=1, parent_chunk_id=parent_id)
                spans.append(child)
        return spans
