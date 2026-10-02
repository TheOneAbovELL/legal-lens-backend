"""Chunking strategy interface and shared metadata construction.

Every strategy splits each legal unit independently (chunks never cross a Section/Article/
paragraph boundary) and returns :class:`Chunk` objects with the same metadata model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator

from app.core.text import count_tokens, sha256
from app.domain.acts import act_display_name
from app.domain.chunks import Chunk, ChunkMetadata, make_chunk_id
from app.domain.documents import BlockType, LegalUnit, StructuredDocument
from app.rag.chunking.segments import Span, make_span


class ChunkingProfile(BaseModel):
    """A named, reproducible chunking configuration (strategy + parameters)."""

    name: str
    strategy: str
    chunk_size: int = Field(default=400, ge=16, le=8192)  # approx tokens
    overlap: int = Field(default=0, ge=0)
    min_chunk_tokens: int = Field(default=0, ge=0)
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("overlap")
    @classmethod
    def _overlap_smaller_than_size(cls, value: int, info: Any) -> int:
        size = info.data.get("chunk_size", 400)
        if value >= size:
            raise ValueError("overlap must be smaller than chunk_size")
        return value


class ChunkingStrategy(ABC):
    strategy_name: ClassVar[str]

    def __init__(self, profile: ChunkingProfile) -> None:
        if profile.strategy != self.strategy_name:
            raise ValueError(f"profile {profile.name} is for {profile.strategy}, not {self.strategy_name}")
        self.profile = profile

    async def chunk(self, document: StructuredDocument) -> list[Chunk]:
        """Split a structured document into chunks (async: some strategies call models)."""
        created_at = datetime.now(UTC)
        chunks: list[Chunk] = []
        for unit in document.units:
            if unit.end <= unit.start:
                continue
            for span in await self.split_unit(document, unit):
                chunks.append(self._make_chunk(document, unit, span, len(chunks), created_at))
        return chunks

    @abstractmethod
    async def split_unit(self, document: StructuredDocument, unit: LegalUnit) -> list[Span]:
        """Return chunk spans (absolute offsets) covering ``unit``."""

    # ------------------------------------------------------------------ helpers
    def block_spans(self, document: StructuredDocument, unit: LegalUnit) -> list[Span]:
        text = document.document.text
        spans = [
            s for b in unit.blocks if (s := make_span(text, b.start, b.end, block_type=b.block_type.value, label=b.label))
        ]
        if not spans:
            whole = make_span(text, unit.start, unit.end)
            spans = [whole] if whole else []
        return spans

    def _make_chunk(
        self, document: StructuredDocument, unit: LegalUnit, span: Span, index: int, created_at: datetime
    ) -> Chunk:
        doc = document.document
        content = doc.text[span.start : span.end]
        content_hash = sha256(content)
        overlapping = [b for b in unit.blocks if b.start < span.end and b.end > span.start]
        sub_label = next(
            (b.label for b in overlapping if b.block_type in (BlockType.SUBSECTION, BlockType.CLAUSE) and b.label), None
        )
        first_block_idx = next((i for i, b in enumerate(unit.blocks) if b.end > span.start), 0)
        paragraph = int(unit.number) if unit.kind.value == "paragraph" and unit.number and unit.number.isdigit() else (
            first_block_idx + 1 if unit.blocks else None
        )
        chunk_id = span.info.get("chunk_id") or make_chunk_id(
            doc.document_id, doc.version, self.profile.name, index, content_hash
        )
        metadata = ChunkMetadata(
            chunk_id=chunk_id,
            document_id=doc.document_id,
            document_version=doc.version,
            source=doc.source,
            title=doc.title,
            document_type=doc.document_type,
            jurisdiction=doc.jurisdiction,
            act=doc.act,
            section=unit.number if unit.kind.value in ("section", "article", "rule") else None,
            unit_kind=unit.kind.value,
            section_heading=unit.heading,
            subsection=sub_label,
            paragraph=paragraph,
            page_number=doc.page_at(span.start),
            case_name=doc.case_name,
            case_citation=doc.case_citation,
            court=doc.court,
            decision_date=doc.decision_date,
            parent_chunk_id=span.info.get("parent_chunk_id"),
            hierarchy_level=span.info.get("level", 1),
            block_types=sorted({b.block_type.value for b in overlapping}),
            chunking_strategy=self.strategy_name,
            chunk_profile=self.profile.name,
            chunk_size=self.profile.chunk_size,
            overlap=self.profile.overlap,
            token_count=count_tokens(content),
            chunk_index=index,
            char_start=span.start,
            char_end=span.end,
            semantic_boundary=span.info.get("semantic_boundary"),
            content_hash=content_hash,
            created_at=created_at,
            effective_date=doc.effective_date,
        )
        return Chunk(content=content, context_header=self._header(document, unit, span, sub_label), metadata=metadata)

    @staticmethod
    def _header(document: StructuredDocument, unit: LegalUnit, span: Span, sub_label: str | None) -> str:
        doc = document.document
        parts = [act_display_name(doc.act) or doc.title]
        if doc.case_name and doc.case_name not in parts:
            parts.append(doc.case_name)
        if unit.chapter:
            parts.append(unit.chapter)
        if unit.number or unit.heading:
            parts.append(unit.display_name)
        if sub_label and span.start > unit.start:
            parts.append(sub_label)
        return " › ".join(p for p in parts if p)
