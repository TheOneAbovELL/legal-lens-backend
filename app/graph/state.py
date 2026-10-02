"""Strongly typed LangGraph state for the single canonical RAG pipeline."""

from __future__ import annotations

import operator
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field

from app.domain.query import ComplexityResult, IntentResult, LegalEntity, SafetyResult, SubQuery
from app.domain.retrieval import (
    BuiltContext,
    Citation,
    EvidenceValidation,
    GenerationResult,
    OutputValidation,
    ProvisionMapping,
    RetrievalFilters,
    RetrievedChunk,
)
from app.rag.profiles import RetrievalProfile
from app.services.generation import UserRole
from app.services.session_memory import SessionTurn


def merge_dicts(left: dict[str, float], right: dict[str, float]) -> dict[str, float]:
    merged = dict(left)
    for key, value in right.items():
        merged[key] = round(merged.get(key, 0.0) + value, 2)
    return merged


class PipelineMode(str, Enum):
    ANSWER = "answer"  # retrieval + grounded generation
    SEARCH = "search"  # retrieval only, no LLM unless explicitly allowed


class Route(str, Enum):
    REFUSE = "refuse"
    SMALL_TALK = "small_talk"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class PipelineOptions(BaseModel):
    mode: PipelineMode = PipelineMode.ANSWER
    allow_llm: bool = True  # False forbids LLM use in planning (search endpoint default)
    streaming: bool = False
    profile_override: str | None = None
    top_k: int | None = None
    filters: RetrievalFilters | None = None
    user_role: UserRole = UserRole.CITIZEN
    session_key: str | None = None


class PipelineError(BaseModel):
    stage: str
    category: str
    message: str
    recoverable: bool = True


class PipelineState(BaseModel):
    request_id: str
    query: str
    options: PipelineOptions = Field(default_factory=PipelineOptions)

    # understanding
    normalized_query: str = ""
    retrieval_query: str = ""
    entities: list[LegalEntity] = Field(default_factory=list)
    history: list[SessionTurn] = Field(default_factory=list)
    follow_up: bool = False
    intent: IntentResult | None = None
    safety: SafetyResult | None = None
    complexity: ComplexityResult | None = None
    route: Route | None = None
    profile: RetrievalProfile | None = None
    profile_mode: str | None = None

    # retrieval
    subqueries: list[SubQuery] = Field(default_factory=list)
    decomposition_method: str | None = None
    retrieval_results: list[RetrievedChunk] = Field(default_factory=list)
    retrieval_source_counts: dict[str, int] = Field(default_factory=dict)
    reranked_results: list[RetrievedChunk] = Field(default_factory=list)
    reranker_used: str | None = None
    context: BuiltContext | None = None
    mappings: list[ProvisionMapping] = Field(default_factory=list)
    evidence: EvidenceValidation | None = None

    # generation
    generation: GenerationResult | None = None
    output_validation: OutputValidation | None = None
    regenerations: int = 0
    corrective_feedback: str | None = None
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    refused: bool = False

    # observability (reducers accumulate across nodes)
    warnings: Annotated[list[str], operator.add] = Field(default_factory=list)
    errors: Annotated[list[PipelineError], operator.add] = Field(default_factory=list)
    timings_ms: Annotated[dict[str, float], merge_dicts] = Field(default_factory=dict)
