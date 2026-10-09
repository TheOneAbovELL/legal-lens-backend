"""Schemas for service, health, readiness and diagnostics endpoints. No secrets ever appear here."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.query import ComplexityResult, IntentResult, SafetyResult, SubQuery

Scalar = str | int | float | bool | None


class RootResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "legal-lens-backend"
    version: str
    docs: str | None = Field(default=None, description="Swagger UI path (absent when docs are disabled)")


class HealthResponse(BaseModel):
    status: Literal["healthy"] = "healthy"


class ComponentStatus(BaseModel):
    name: str
    status: str = Field(description="ok | configured | loading | unavailable | not_configured | disabled | failed")
    required: bool
    detail: dict[str, Scalar] = Field(default_factory=dict)
    error: str | None = Field(default=None, description="Error class/summary; never credentials")


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str] = Field(description="component -> status")
    failed: list[str] = Field(default_factory=list, description="Required components that are not usable")
    components: list[ComponentStatus]

    model_config = {"json_schema_extra": {"example": {
        "status": "ready",
        "checks": {"application": "ok", "embedding": "ok", "qdrant": "ok", "database": "ok", "llm": "configured",
                   "knowledge_graph": "disabled"},
        "failed": [],
        "components": [{"name": "qdrant", "status": "ok", "required": True,
                        "detail": {"mode": "local", "collection": "legal-lens-chunks", "points": 23}}],
    }}}


# ------------------------------------------------------------------ diagnostics
class QdrantDiagnostics(BaseModel):
    reachable: bool
    mode: str
    target: str = Field(description="Host or local path (no credentials)")
    collection: str
    collection_exists: bool
    points: int | None = None
    dense_vector: str | None = None
    vector_dimension: int | None = None
    expected_dimension: int
    distance: str | None = None
    sparse_vector: str | None = None
    sparse_enabled: bool
    text_search_field: str | None = Field(
        default=None, description="Payload field with a full-text index; enables the keyword ('lexical') source"
    )
    indexed_chunk_profiles: list[str] | None = None
    test_query_ok: bool | None = Field(default=None, description="Read-only dense query with a probe vector")
    test_query_hits: int | None = None
    latency_ms: float
    error: str | None = None


class EmbeddingDiagnostics(BaseModel):
    ok: bool
    model: str
    model_version: str
    loaded: bool
    expected_dimension: int
    dimension: int | None = None
    finite: bool | None = None
    non_zero: bool | None = None
    l2_norm: float | None = Field(default=None, description="≈1.0 when embeddings are normalized")
    normalized: bool | None = None
    latency_ms: float
    error: str | None = None


class LLMCheckRequest(BaseModel):
    prompt: str = Field(default="Respond with OK.", max_length=200)
    max_tokens: int = Field(default=64, ge=1, le=256)


class LLMDiagnostics(BaseModel):
    ok: bool
    configured_providers: list[str]
    provider: str | None = None
    model: str | None = None
    attempts: int | None = None
    response_preview: str | None = Field(default=None, description="First 80 characters of the reply")
    total_tokens: int | None = None
    latency_ms: float
    error: str | None = None


class RouteRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    use_llm_decomposition: bool = Field(
        default=False, description="Use the LLM decomposer for COMPLEX queries (costs tokens); default rule-based"
    )

    model_config = {"json_schema_extra": {"examples": [
        {"query": "What is Article 21?"},
        {"query": "Explain the difference between Article 14 and Article 21."},
        {"query": "Compare the legal consequences under IPC 420 and BNS 318, analyze how the change affects an "
                   "accused person, and cite the relevant authorities."},
    ]}}


class RouteDiagnostics(BaseModel):
    query: str
    normalized_query: str
    entities: list[str]
    intent: IntentResult
    safety: SafetyResult
    would_refuse: bool
    complexity: ComplexityResult | None = None
    retrieval_profile: str | None = None
    route: str | None = None
    profile_selection: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    reranker: str | None = None
    decomposition_method: str | None = None
    subqueries: list[SubQuery] = Field(default_factory=list)


class ConfigSummary(BaseModel):
    environment: str
    version: str
    diagnostics_enabled: bool
    auth_required: bool
    registration_enabled: bool
    rate_limit: str
    vector_store: str
    embedding_model: str
    embedding_dimension: int
    reranker_model: str
    llm_targets: list[str]
    llm_api_key_configured: bool
    knowledge_graph_enabled: bool
    complexity_routing_enabled: bool
    decomposition: str
    default_chunk_profile: str
    adaptive_selection_mode: str
    session_memory_enabled: bool
