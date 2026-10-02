"""Search endpoint: structured hybrid-retrieval results from the canonical pipeline (search mode).

No LLM is called unless ``generate_answer`` is true (query planning is rule-based in search mode).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.api.deps import ContainerDep, OptionalUser, RateLimited
from app.api.errors import responses
from app.api.v1.common import build_options, check_query, public_result, request_id
from app.core.config import Settings
from app.domain.retrieval import EvidenceItem
from app.graph.runner import PipelineResult
from app.graph.state import PipelineMode
from app.schemas.common import BnsAlert
from app.schemas.search import SEARCH_EXAMPLES, RetrievalMetadata, SearchRequest, SearchResponse, SearchResult

router = APIRouter(tags=["Search"])
SNIPPET_CHARS = 300


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET_CHARS else text[:SNIPPET_CHARS].rsplit(" ", 1)[0] + " …"


def to_search_response(query: str, result: PipelineResult, top_k: int, settings: Settings) -> SearchResponse:
    result = public_result(result, settings)
    meta = result.metadata
    alerts = {(m.source_act, m.source_section.split("(")[0]): BnsAlert.from_mapping(m) for m in result.mappings}
    results: list[SearchResult] = []
    # Exact matches on provisions the user named come first, then by relevance.
    ranked = sorted(result.evidence, key=lambda c: ({'metadata', 'graph'}.isdisjoint(c.scores), -c.final_score))
    for rank, chunk in enumerate(ranked[:top_k], start=1):
        md = chunk.metadata
        citation = next((c for c in result.citations if c.chunk_id == chunk.chunk_id), None)
        if citation is None:
            citation = EvidenceItem(citation_id=f"C{rank}", chunk=chunk, token_count=0).citation()
        results.append(SearchResult(
            document_id=md.document_id,
            chunk_id=chunk.chunk_id,
            title=md.title,
            case_name=md.case_name,
            snippet=_snippet(chunk.content),
            content=chunk.content,
            score=round(chunk.fused_score, 6),
            rerank_score=chunk.rerank_score,
            relevance_score=round(chunk.final_score, 6),
            retrieval_sources=chunk.sources,
            citation=citation,
            metadata=md,
            bns_alert=alerts.get((md.act or "", md.section or "")),
        ))
    return SearchResponse(
        query=query,
        request_id=meta.request_id,
        results=results,
        total=len(results),
        processing_time_ms=meta.latency_ms,
        answer=result.answer,
        bns_alerts=list(alerts.values()),
        warnings=result.warnings,
        retrieval_metadata=RetrievalMetadata(
            strategy=meta.retrieval_profile,
            complexity=meta.complexity.complexity.value if meta.complexity else None,
            route=meta.route,
            reranker=meta.reranker,
            chunk_profiles=meta.chunk_profiles,
            subqueries=len(meta.subqueries),
            sources=meta.retrieval_sources,
            candidates=meta.candidates,
            latency_ms=meta.latency_ms,
            timings_ms=meta.timings_ms,
        ),
        diagnostics=result.diagnostics,
    )


async def _search(body: SearchRequest, container, user) -> SearchResponse:  # type: ignore[no-untyped-def]
    query = check_query(container, body.query)
    options = build_options(
        mode=PipelineMode.ANSWER if body.generate_answer else PipelineMode.SEARCH,
        user=user, profile=body.profile, filters=body.filters, top_k=body.top_k, allow_llm=body.generate_answer,
    )
    result = await container.pipeline.run(request_id(), query, options)
    return to_search_response(query, result, body.top_k, container.settings)


_DESCRIPTION = (
    "Structured hybrid retrieval through the canonical pipeline in **search mode**: routing, query planning, "
    "dense + sparse + exact-provision (+ graph) retrieval, fusion, reranking and context selection — "
    "**no LLM call** unless `generate_answer` is true (planning is rule-based). Use `diagnostics` to see which "
    "retrieval stages actually ran and how many candidates each produced."
)


@router.post("/search", response_model=SearchResponse, dependencies=[RateLimited], summary="Search legal sources",
             description=_DESCRIPTION, responses=responses(401, 413, 422, 429, 502, 503, 504))
async def search(
    container: ContainerDep,
    user: OptionalUser,
    body: Annotated[SearchRequest | None, Body(openapi_examples=SEARCH_EXAMPLES)] = None,
    query: str | None = Query(default=None, max_length=8000, description="Legacy: query as URL parameter"),
) -> SearchResponse:
    if body is None:
        body = SearchRequest(query=query or "")
    return await _search(body, container, user)


@router.get("/search", response_model=SearchResponse, dependencies=[RateLimited], summary="Search (GET, legacy)",
            description="Same as POST /api/v1/search with only `query` and `top_k`.", responses=responses(401, 422, 429, 503))
async def search_get(
    container: ContainerDep,
    user: OptionalUser,
    query: str = Query(min_length=1, max_length=8000),
    top_k: int = Query(default=10, ge=1, le=50),
) -> SearchResponse:
    return await _search(SearchRequest(query=query, top_k=top_k), container, user)
