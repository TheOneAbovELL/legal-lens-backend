"""Search API schemas (structured retrieval results; no LLM unless ``generate_answer``)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.chunks import ChunkMetadata
from app.domain.retrieval import Citation
from app.graph.runner import RetrievalDiagnostics
from app.schemas.common import BnsAlert, ProfileName, SearchFilters

SEARCH_EXAMPLES = {
    "provision": {"summary": "Exact provision (metadata + dense + sparse)", "value": {"query": "Section 302 IPC", "top_k": 5}},
    "concept": {"summary": "Concept search", "value": {"query": "punishment for theft", "top_k": 5}},
    "filtered": {"summary": "Filtered to one act", "value": {"query": "punishment for murder", "top_k": 5,
                                                              "filters": {"acts": ["BNS"]}}},
    "complex": {"summary": "Complex query (rule-based decomposition, still no LLM)",
                "value": {"query": "Compare IPC 420 and BNS 318 and explain the impact of the change", "top_k": 8}},
}


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000, description="Search text")
    top_k: int = Field(default=10, ge=1, le=50, description="Number of results")
    filters: SearchFilters | None = None
    profile: ProfileName | None = Field(default=None, description="Force a retrieval profile (default: adaptive)")
    generate_answer: bool = Field(default=False, description="Also run grounded generation (calls the LLM)")

    model_config = {"json_schema_extra": {"example": SEARCH_EXAMPLES["provision"]["value"]}}


class SearchResult(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    case_name: str | None = None
    snippet: str = Field(description="First ~300 characters")
    content: str = Field(description="Full chunk text")
    score: float = Field(description="Hybrid fusion score (weighted reciprocal rank fusion)")
    rerank_score: float | None = Field(default=None, description="Reranker relevance in [0, 1]")
    relevance_score: float = Field(description="Final ranking score (rerank score when reranked)")
    retrieval_sources: list[str] = Field(description="Retrievers that returned this chunk: dense/sparse/metadata/graph")
    citation: Citation
    metadata: ChunkMetadata
    bns_alert: BnsAlert | None = None


class RetrievalMetadata(BaseModel):
    strategy: str | None = Field(description="Retrieval profile: FAST / BALANCED / DEEP")
    complexity: str | None
    route: str | None
    reranker: str | None
    chunk_profiles: list[str] | None
    subqueries: int
    sources: dict[str, int] = Field(description="Raw hits per retrieval source")
    candidates: int = Field(description="Unique candidates after fusion")
    latency_ms: float
    timings_ms: dict[str, float]


class SearchResponse(BaseModel):
    query: str
    request_id: str
    results: list[SearchResult]
    total: int
    processing_time_ms: float
    answer: str | None = None
    bns_alerts: list[BnsAlert]
    warnings: list[str]
    retrieval_metadata: RetrievalMetadata
    diagnostics: RetrievalDiagnostics | None = Field(
        default=None, description="Stage-by-stage diagnostics (non-production environments only)"
    )
