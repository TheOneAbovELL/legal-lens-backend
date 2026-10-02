"""Query-understanding models: entities, intent, safety, complexity, sub-queries."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    SECTION = "section"
    ARTICLE = "article"
    ACT = "act"
    CASE_CITATION = "case_citation"


class LegalEntity(BaseModel):
    type: EntityType
    value: str  # "420", "21", "IPC", "Maneka Gandhi v. Union of India"
    act: str | None = None  # canonical act code: IPC, BNS, CONSTITUTION ...
    raw: str

    @property
    def key(self) -> str:
        return f"{self.act or '?'}:{self.type.value}:{self.value}".upper()


class Intent(str, Enum):
    STATUTE_LOOKUP = "statute_lookup"
    PROVISION_MAPPING = "provision_mapping"
    CASE_LAW = "case_law"
    PROCEDURAL = "procedural"
    DOCUMENT_ANALYSIS = "document_analysis"
    GENERAL_LEGAL = "general_legal"
    SMALL_TALK = "small_talk"


class IntentResult(BaseModel):
    intent: Intent
    confidence: float
    signals: list[str] = Field(default_factory=list)


class SafetyDecision(str, Enum):
    ALLOW = "allow"
    ALLOW_WITH_CAUTION = "allow_with_caution"
    REFUSE = "refuse"


class SafetyResult(BaseModel):
    decision: SafetyDecision
    categories: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    jurisdiction_note: str | None = None
    requires_disclaimer: bool = True

    @property
    def allowed(self) -> bool:
        return self.decision != SafetyDecision.REFUSE


class Complexity(str, Enum):
    SIMPLE = "SIMPLE"
    MODERATE = "MODERATE"
    COMPLEX = "COMPLEX"


class EvidenceLevel(str, Enum):
    SINGLE_SOURCE = "single_source"
    MULTI_SOURCE = "multi_source"
    CROSS_DOCUMENT = "cross_document"


class ComplexityResult(BaseModel):
    complexity: Complexity
    confidence: float
    score: float
    reasons: list[str] = Field(default_factory=list)
    features: dict[str, float] = Field(default_factory=dict)
    detected_entities: list[LegalEntity] = Field(default_factory=list)
    requires_decomposition: bool = False
    requires_reranking: bool = False
    requires_multi_hop: bool = False
    evidence_level: EvidenceLevel = EvidenceLevel.SINGLE_SOURCE


class SubQuery(BaseModel):
    subquery_id: str
    query: str
    purpose: str
    required_evidence: str = ""
    legal_entities: list[str] = Field(default_factory=list)
    priority: int = Field(default=1, ge=0, le=5)  # 0 = highest
    depends_on: list[str] = Field(default_factory=list)


class DecompositionResult(BaseModel):
    subqueries: list[SubQuery]
    method: str  # "none" | "expansion" | "rule" | "llm" | "rule_fallback"
    warnings: list[str] = Field(default_factory=list)
