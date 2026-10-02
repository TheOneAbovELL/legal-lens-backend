"""Document and legal-structure models produced by the ingestion front half."""

from __future__ import annotations

from bisect import bisect_right
from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    STATUTE = "statute"
    CONSTITUTION = "constitution"
    CASE_LAW = "case_law"
    REGULATION = "regulation"
    COMMENTARY = "commentary"
    OTHER = "other"


class UnitKind(str, Enum):
    """Top-level logical unit inside a document."""

    SECTION = "section"
    ARTICLE = "article"
    RULE = "rule"
    SCHEDULE = "schedule"
    PARAGRAPH = "paragraph"  # numbered judgment paragraph
    BODY = "body"  # unstructured text / preamble


class BlockType(str, Enum):
    """Sub-unit block. Blocks are the atomic boundaries legal-aware chunkers prefer."""

    HEADING = "heading"
    TEXT = "text"
    SUBSECTION = "subsection"
    CLAUSE = "clause"
    EXPLANATION = "explanation"
    PROVISO = "proviso"
    ILLUSTRATION = "illustration"
    EXCEPTION = "exception"
    DEFINITION = "definition"


class SourceDocument(BaseModel):
    document_id: str
    version: str
    title: str
    source: str
    document_type: DocumentType = DocumentType.OTHER
    jurisdiction: str = "IN"
    act: str | None = None
    effective_date: date | None = None
    publication_date: date | None = None
    content_hash: str
    text: str
    case_name: str | None = None
    case_citation: str | None = None
    court: str | None = None
    decision_date: date | None = None
    #: Character offsets at which each page starts (page 1 at index 0). Empty when unknown.
    page_offsets: list[int] = Field(default_factory=list)

    def page_at(self, offset: int) -> int | None:
        if not self.page_offsets:
            return None
        return bisect_right(self.page_offsets, offset)


class LegalBlock(BaseModel):
    block_type: BlockType
    label: str | None = None  # e.g. "(1)", "Explanation 2", "(a)"
    start: int  # absolute char offsets into SourceDocument.text
    end: int


class LegalUnit(BaseModel):
    unit_id: str
    kind: UnitKind
    number: str | None = None  # "420", "21", "304B"
    heading: str | None = None
    part: str | None = None
    chapter: str | None = None
    start: int
    end: int
    blocks: list[LegalBlock] = Field(default_factory=list)

    @property
    def display_name(self) -> str:
        if self.number:
            label = f"{self.kind.value.capitalize()} {self.number}"
            return f"{label} — {self.heading}" if self.heading else label
        return self.heading or self.kind.value.capitalize()


class StructuredDocument(BaseModel):
    document: SourceDocument
    units: list[LegalUnit]

    def text_of(self, start: int, end: int) -> str:
        return self.document.text[start:end]
