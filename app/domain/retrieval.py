"""Retrieval, evidence, context and answer models."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field

from app.domain.chunks import ChunkMetadata


class RetrievalFilters(BaseModel):
    """Store-agnostic metadata filters. Translated to Qdrant filters by the vector store."""

    document_ids: list[str] | None = None
    document_types: list[str] | None = None
    acts: list[str] | None = None
    sections: list[str] | None = None
    jurisdiction: str | None = None
    chunk_profiles: list[str] | None = None
    courts: list[str] | None = None
    decided_after: date | None = None
    decided_before: date | None = None
    only_latest: bool = True

    def merged(self, **overrides: object) -> RetrievalFilters:
        data = self.model_dump()
        data.update({k: v for k, v in overrides.items() if v is not None})
        return RetrievalFilters(**data)


class RetrievedChunk(BaseModel):
    chunk_id: str
    content: str
    context_header: str = ""
    metadata: ChunkMetadata
    #: Raw score per retriever source ("dense", "sparse", "metadata", "graph").
    scores: dict[str, float] = Field(default_factory=dict)
    #: 1-based rank per retriever source.
    ranks: dict[str, int] = Field(default_factory=dict)
    fused_score: float = 0.0
    rerank_score: float | None = None
    subquery_ids: list[str] = Field(default_factory=list)
    #: Best (lowest) rank this chunk achieved for each sub-query, across retrieval sources.
    subquery_ranks: dict[str, int] = Field(default_factory=dict)

    def primary_subquery(self, priorities: dict[str, int]) -> str | None:
        """The sub-query this chunk answers best: lowest rank, then highest priority."""
        if not self.subquery_ranks:
            return self.subquery_ids[0] if self.subquery_ids else None
        return min(self.subquery_ranks, key=lambda sid: (self.subquery_ranks[sid], priorities.get(sid, 9)))

    @property
    def final_score(self) -> float:
        return self.rerank_score if self.rerank_score is not None else self.fused_score

    @property
    def sources(self) -> list[str]:
        return sorted(self.scores)


class Citation(BaseModel):
    citation_id: str
    document_id: str
    document_version: str | None = None
    title: str
    act: str | None = None
    section: str | None = None
    section_heading: str | None = None
    subsection: str | None = None
    paragraph: int | None = None
    page: int | None = None
    case_name: str | None = None
    court: str | None = None
    source: str
    chunk_id: str | None = None
    retrieval_sources: list[str] = Field(default_factory=list)
    score: float | None = None
    excerpt: str = Field(default="", description="Leading text of the cited passage (bounded)")


EXCERPT_CHARS = 700


def make_excerpt(text: str, limit: int = EXCERPT_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return cut[: cut.rfind(" ")] + "…" if " " in cut else cut + "…"


class EvidenceItem(BaseModel):
    citation_id: str
    chunk: RetrievedChunk
    token_count: int

    def citation(self) -> Citation:
        md = self.chunk.metadata
        return Citation(
            citation_id=self.citation_id,
            document_id=md.document_id,
            document_version=md.document_version,
            title=md.title,
            act=md.act,
            section=md.section,
            section_heading=md.section_heading,
            subsection=md.subsection,
            paragraph=md.paragraph,
            page=md.page_number,
            case_name=md.case_name,
            court=md.court,
            source=md.source,
            chunk_id=md.chunk_id,
            retrieval_sources=self.chunk.sources,
            score=round(self.chunk.final_score, 6),
            excerpt=make_excerpt(self.chunk.content),
        )


class EvidenceGroup(BaseModel):
    """Evidence from the same document unit (e.g. one statutory section), in document order."""

    group_key: str
    title: str
    items: list[EvidenceItem]


class BuiltContext(BaseModel):
    groups: list[EvidenceGroup] = Field(default_factory=list)
    token_count: int = 0
    candidates_considered: int = 0
    dropped_duplicates: int = 0
    dropped_low_relevance: int = 0
    dropped_budget: int = 0

    @property
    def items(self) -> list[EvidenceItem]:
        return [item for group in self.groups for item in group.items]

    def citations(self) -> list[Citation]:
        return [item.citation() for item in self.items]


class MappingType(str, Enum):
    EXACT = "exact"
    APPROXIMATE = "approximate"
    AMBIGUOUS = "ambiguous"
    NO_MAPPING = "no_mapping"
    UNKNOWN = "unknown"  # not present in the mapping dataset


class ProvisionMapping(BaseModel):
    citation_id: str | None = None  # "M1".. when included in the LLM context
    source_act: str
    source_section: str
    target_act: str
    target_sections: list[str] = Field(default_factory=list)
    mapping_type: MappingType
    subject: str | None = None
    notes: str | None = None
    provenance: str
    verification_status: str
    effective_date: date | None = None

    def describe(self) -> str:
        src = f"{self.source_act} Section {self.source_section}"
        if self.mapping_type == MappingType.UNKNOWN:
            return f"{src}: no entry in the mapping dataset (mapping unknown)."
        if self.mapping_type == MappingType.NO_MAPPING:
            return f"{src}: no corresponding provision in {self.target_act}. {self.notes or ''}".strip()
        targets = ", ".join(f"{self.target_act} Section {t}" for t in self.target_sections)
        subject = f" ({self.subject})" if self.subject else ""
        notes = f" Note: {self.notes}" if self.notes else ""
        when = f" Effective {self.effective_date.isoformat()}." if self.effective_date else ""
        return f"{src}{subject} -> {targets} [{self.mapping_type.value} mapping].{when}{notes}"


class EvidenceValidation(BaseModel):
    sufficient: bool
    evidence_count: int
    uncovered_subqueries: list[str] = Field(default_factory=list)
    missing_provisions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TokenUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class GenerationResult(BaseModel):
    text: str
    provider: str
    model: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    attempts: int = 1


class OutputValidation(BaseModel):
    valid: bool
    cited_ids: list[str] = Field(default_factory=list)
    invalid_citation_ids: list[str] = Field(default_factory=list)
    unsupported_references: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    regenerated: bool = False
