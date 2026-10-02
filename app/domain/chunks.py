"""Chunk model and metadata shared by every chunking strategy and the vector index."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.documents import DocumentType

# Fixed namespace so chunk IDs are deterministic across runs and machines.
CHUNK_NAMESPACE = uuid.UUID("7c0f8f3e-3c55-4a8b-9f3a-6f1f1f2b9d10")


def make_chunk_id(document_id: str, version: str, profile: str, index: int | str, content_hash: str) -> str:
    return str(uuid.uuid5(CHUNK_NAMESPACE, f"{document_id}|{version}|{profile}|{index}|{content_hash}"))


class ChunkMetadata(BaseModel):
    chunk_id: str
    document_id: str
    document_version: str
    source: str
    title: str
    document_type: DocumentType
    jurisdiction: str
    act: str | None = None
    section: str | None = None  # unit number, e.g. "420" or "21"
    unit_kind: str | None = None  # section | article | paragraph | body ...
    section_heading: str | None = None
    subsection: str | None = None  # first subsection/clause label covered
    paragraph: int | None = None  # paragraph ordinal inside the unit
    page_number: int | None = None
    # Case-law metadata (judgments); empty for statutes.
    case_name: str | None = None
    case_citation: str | None = None
    court: str | None = None
    decision_date: date | None = None
    parent_chunk_id: str | None = None
    hierarchy_level: int = 1  # 0 = parent/unit level, 1 = leaf
    block_types: list[str] = Field(default_factory=list)
    chunking_strategy: str
    chunk_profile: str
    chunk_size: int  # configured target size (approx tokens)
    overlap: int
    token_count: int
    chunk_index: int
    char_start: int
    char_end: int
    semantic_boundary: dict[str, Any] | None = None
    content_hash: str
    created_at: datetime
    effective_date: date | None = None
    is_latest: bool = True
    embedding_model: str | None = None
    embedding_version: str | None = None


class Chunk(BaseModel):
    content: str
    #: Short contextual header (act › section heading) prepended for embedding and display.
    context_header: str = ""
    metadata: ChunkMetadata

    @property
    def chunk_id(self) -> str:
        return self.metadata.chunk_id

    @property
    def embedding_text(self) -> str:
        return f"{self.context_header}\n{self.content}" if self.context_header else self.content
