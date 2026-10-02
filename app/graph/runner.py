"""PipelineService: runs the canonical graph for JSON responses and SSE streaming.

Both modes execute the same compiled graph; streaming uses LangGraph's ``updates`` (stage events)
and ``custom`` (real LLM token deltas written by the generate node) stream modes.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field

from app.core.exceptions import AppError, PipelineTimeoutError
from app.core.logging import get_logger
from app.domain.query import ComplexityResult, IntentResult, SafetyResult, SubQuery
from app.domain.retrieval import (
    Citation,
    EvidenceValidation,
    OutputValidation,
    ProvisionMapping,
    RetrievedChunk,
    TokenUsage,
)
from app.graph.state import PipelineMode, PipelineOptions, PipelineState
from app.services.safety import DISCLAIMER
from app.services.session_memory import SessionMemory, SessionTurn

logger = get_logger(__name__)


class PipelineMetadata(BaseModel):
    """Safe, structured observability metadata (no prompts, no chain-of-thought)."""

    request_id: str
    intent: IntentResult | None = None
    safety: SafetyResult | None = None
    complexity: ComplexityResult | None = None
    route: str | None = None
    retrieval_profile: str | None = None
    profile_selection: list[str] = Field(default_factory=list)
    chunk_profiles: list[str] | None = None
    decomposition_method: str | None = None
    subqueries: list[SubQuery] = Field(default_factory=list)
    retrieval_sources: dict[str, int] = Field(default_factory=dict)
    candidates: int = 0
    reranker: str | None = None
    evidence_selected: int = 0
    context_tokens: int = 0
    evidence: EvidenceValidation | None = None
    output_validation: OutputValidation | None = None
    provider: str | None = None
    model: str | None = None
    llm_attempts: int | None = None
    token_usage: TokenUsage | None = None
    follow_up: bool = False
    timings_ms: dict[str, float] = Field(default_factory=dict)
    latency_ms: float = 0.0
    errors: list[str] = Field(default_factory=list)


class SourceDiagnostics(BaseModel):
    executed: bool = Field(description="The source was queried for this request")
    hits: int = Field(description="Raw hits returned across all sub-queries")
    latency_ms: float | None = None
    error: str | None = None


class StageDiagnostics(BaseModel):
    executed: bool
    count: int = Field(description="Items produced by this stage")
    latency_ms: float | None = None
    method: str | None = None


class ContextDiagnostics(BaseModel):
    executed: bool
    selected_chunks: int
    groups: int
    context_tokens: int
    dropped_duplicates: int
    dropped_low_relevance: int
    dropped_budget: int


class RetrievalDiagnostics(BaseModel):
    """What actually ran, derived from graph state (not configuration)."""

    complexity: str | None
    retrieval_profile: str | None
    route: str | None
    retrieval_mode: str = Field(description="hybrid when more than one retrieval source executed")
    subqueries: list[SubQuery]
    sources: dict[str, SourceDiagnostics]
    fusion: StageDiagnostics
    reranking: StageDiagnostics
    context: ContextDiagnostics
    provision_mapping: StageDiagnostics
    generation: StageDiagnostics
    latency_ms: dict[str, float] = Field(description="dense includes query embedding; total is end-to-end")


def build_diagnostics(state: PipelineState, latency_ms: float) -> RetrievalDiagnostics:
    t = state.timings_ms
    attempted = state.profile.sources if state.profile and state.retrieval_results is not None and "retrieval" in t else []
    errors = {e.message.split(":", 1)[0]: e.message.split(":", 1)[-1].strip()
              for e in state.errors if e.stage == "retrieval"}
    sources = {
        name: SourceDiagnostics(
            executed=name in attempted, hits=state.retrieval_source_counts.get(name, 0),
            latency_ms=t.get(f"retrieval.{name}"), error=errors.get(name),
        )
        for name in ("dense", "sparse", "metadata", "graph")
    }
    succeeded = [n for n, s in sources.items() if s.executed and not s.error]
    mode = "hybrid" if len(succeeded) > 1 else (succeeded[0] if succeeded else "none")
    ctx = state.context
    return RetrievalDiagnostics(
        complexity=state.complexity.complexity.value if state.complexity else None,
        retrieval_profile=state.profile.name if state.profile else None,
        route=state.route.value if state.route else None,
        retrieval_mode=mode,
        subqueries=state.subqueries,
        sources=sources,
        fusion=StageDiagnostics(executed="retrieval" in t, count=len(state.retrieval_results),
                                latency_ms=t.get("retrieval"), method="weighted reciprocal rank fusion"),
        reranking=StageDiagnostics(executed="rerank" in t, count=len(state.reranked_results),
                                   latency_ms=t.get("rerank"), method=state.reranker_used),
        context=ContextDiagnostics(
            executed=ctx is not None, selected_chunks=len(ctx.items) if ctx else 0,
            groups=len(ctx.groups) if ctx else 0, context_tokens=ctx.token_count if ctx else 0,
            dropped_duplicates=ctx.dropped_duplicates if ctx else 0,
            dropped_low_relevance=ctx.dropped_low_relevance if ctx else 0,
            dropped_budget=ctx.dropped_budget if ctx else 0,
        ),
        provision_mapping=StageDiagnostics(executed="provision_mapping" in t, count=len(state.mappings),
                                           latency_ms=t.get("provision_mapping")),
        generation=StageDiagnostics(executed=state.generation is not None,
                                    count=state.regenerations + 1 if state.generation else 0,
                                    latency_ms=t.get("generation"),
                                    method=f"{state.generation.provider}:{state.generation.model}" if state.generation else None),
        latency_ms={**{k: v for k, v in t.items() if "." not in k}, "total": round(latency_ms, 2)},
    )


class PipelineResult(BaseModel):
    answer: str | None
    refused: bool
    citations: list[Citation]
    mappings: list[ProvisionMapping]
    evidence: list[RetrievedChunk]
    warnings: list[str]
    disclaimer: str | None
    metadata: PipelineMetadata
    diagnostics: RetrievalDiagnostics | None = None


def build_result(state: PipelineState, latency_ms: float) -> PipelineResult:
    context = state.context
    generation = state.generation
    if generation is not None:
        citations = state.citations
    elif state.options.mode == PipelineMode.SEARCH and context is not None:
        citations = context.citations()
    else:
        citations = []  # refusals / insufficient evidence: nothing was used to support an answer
    evidence = [item.chunk for item in context.items] if context else []
    disclaimer = DISCLAIMER if not state.safety or state.safety.requires_disclaimer else None
    meta = PipelineMetadata(
        request_id=state.request_id,
        intent=state.intent,
        safety=state.safety,
        complexity=state.complexity,
        route=state.route.value if state.route else None,
        retrieval_profile=state.profile.name if state.profile else None,
        profile_selection=state.profile.selection_reasons if state.profile else [],
        chunk_profiles=state.profile.chunk_profiles if state.profile else None,
        decomposition_method=state.decomposition_method,
        subqueries=state.subqueries,
        retrieval_sources=state.retrieval_source_counts,
        candidates=len(state.retrieval_results),
        reranker=state.reranker_used,
        evidence_selected=len(evidence),
        context_tokens=context.token_count if context else 0,
        evidence=state.evidence,
        output_validation=state.output_validation,
        provider=generation.provider if generation else None,
        model=generation.model if generation else None,
        llm_attempts=generation.attempts if generation else None,
        token_usage=generation.usage if generation else None,
        follow_up=state.follow_up,
        timings_ms=state.timings_ms,
        latency_ms=round(latency_ms, 2),
        errors=[f"{e.stage}:{e.category}:{e.message}" for e in state.errors],
    )
    return PipelineResult(
        answer=state.answer,
        refused=state.refused,
        citations=citations,
        mappings=state.mappings,
        evidence=evidence,
        warnings=list(dict.fromkeys(state.warnings)),
        disclaimer=disclaimer,
        metadata=meta,
        diagnostics=build_diagnostics(state, latency_ms),
    )


def result_status(result: PipelineResult) -> str:
    """complete | refused | insufficient_evidence | small_talk — the frontend renders each differently."""
    if result.refused:
        return "refused"
    meta = result.metadata
    if meta.intent is not None and meta.intent.intent.value == "small_talk":
        return "small_talk"
    if meta.evidence is not None and not meta.evidence.sufficient:
        return "insufficient_evidence"
    return "complete"


def analysis_summary(state: dict[str, Any]) -> dict[str, Any]:
    """Public query analysis (typed in app/schemas/chat.py as QueryAnalysis)."""
    intent, safety, complexity, profile, route = (state.get(k) for k in ("intent", "safety", "complexity", "profile", "route"))
    return {
        "intent": intent.intent.value if intent else None,
        "complexity": complexity.complexity.value if complexity else None,
        "confidence": round(complexity.confidence, 3) if complexity else None,
        "route": route.value if route else None,
        "retrieval_profile": profile.name if profile else None,
        "safety_decision": safety.decision.value if safety else None,
        "jurisdiction": "IN",
        "outside_jurisdiction": bool(safety and "foreign_jurisdiction" in safety.categories),
        "decomposition_needed": bool(complexity and complexity.requires_decomposition),
        "comparison_required": bool(complexity and complexity.features.get("comparison", 0) > 0),
        "provisions": [e.raw for e in (complexity.detected_entities if complexity else [])][:10],
        "follow_up": bool(state.get("follow_up", False)),
    }


def trim_for_public(result: PipelineResult) -> PipelineResult:
    """Production view: drops diagnostic detail (sub-queries, timings, errors, stage diagnostics)."""
    meta = result.metadata.model_copy(update={"subqueries": [], "timings_ms": {}, "errors": [],
                                              "profile_selection": [], "chunk_profiles": None})
    return result.model_copy(update={"metadata": meta, "diagnostics": None})


def _stage_event(node: str, update: dict[str, Any]) -> dict[str, Any] | None:
    """Translate a node's state update into a public SSE event (or None)."""
    if node == "understand":
        intent = update.get("intent")
        return {"type": "intent", "intent": intent.intent.value if intent else None,
                "confidence": intent.confidence if intent else None,
                "entities": [e.raw for e in update.get("entities", [])], "follow_up": update.get("follow_up", False)}
    if node == "safety":
        safety = update["safety"]
        return {"type": "safety", "decision": safety.decision.value, "categories": safety.categories}
    if node == "classify":
        c, p = update["complexity"], update["profile"]
        return {"type": "complexity", "complexity": c.complexity.value, "confidence": c.confidence,
                "reasons": c.reasons[:5], "profile": p.name, "route": update["route"].value}
    if node.startswith("plan_"):
        return {"type": "plan", "method": update.get("decomposition_method"),
                "subqueries": [{"id": s.subquery_id, "query": s.query, "purpose": s.purpose}
                               for s in update.get("subqueries", [])]}
    if node == "retrieve":
        return {"type": "retrieval", "candidates": len(update.get("retrieval_results", [])),
                "sources": update.get("retrieval_source_counts", {})}
    if node == "rerank":
        return {"type": "reranking", "reranker": update.get("reranker_used"),
                "count": len(update.get("reranked_results", []))}
    if node == "fuse":
        context = update["context"]
        return {"type": "evidence", "count": len(context.items), "context_tokens": context.token_count,
                "citations": [c.model_dump(mode="json") for c in context.citations()]}
    if node == "map_provisions":
        maps = update.get("mappings", [])
        return {"type": "bns_alert", "mappings": [m.model_dump(mode="json") for m in maps]} if maps else None
    if node == "validate_answer" and update.get("answer") is None:
        return {"type": "status", "message": "answer failed verification; regenerating"}
    return None


class PipelineService:
    def __init__(self, graph: Any, *, timeout: float, memory: SessionMemory | None, diagnostics: bool = True) -> None:
        self._graph = graph
        self._diagnostics = diagnostics
        self._timeout = timeout
        self._memory = memory

    def _initial(self, request_id: str, query: str, options: PipelineOptions) -> dict[str, Any]:
        return {"request_id": request_id, "query": query, "options": options}

    def _remember(self, state: PipelineState) -> None:
        if self._memory is None or not state.options.session_key or state.refused or not state.answer:
            return
        self._memory.add(state.options.session_key, SessionTurn(
            query=state.normalized_query or state.query, answer_preview=state.answer[:300], entities=state.entities,
        ))

    def _log(self, state: PipelineState, latency_ms: float) -> None:
        logger.info("pipeline completed", extra={
            "intent": state.intent.intent.value if state.intent else None,
            "complexity": state.complexity.complexity.value if state.complexity else None,
            "route": state.route.value if state.route else None,
            "profile": state.profile.name if state.profile else None,
            "subqueries": len(state.subqueries),
            "candidates": len(state.retrieval_results),
            "evidence": len(state.context.items) if state.context else 0,
            "provider": state.generation.provider if state.generation else None,
            "model": state.generation.model if state.generation else None,
            "refused": state.refused,
            "latency_ms": round(latency_ms, 2),
            "error_categories": sorted({e.category for e in state.errors}),
        })

    async def run(self, request_id: str, query: str, options: PipelineOptions) -> PipelineResult:
        start = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout):
                raw = await self._graph.ainvoke(self._initial(request_id, query, options), config={"recursion_limit": 40})
        except TimeoutError as exc:
            raise PipelineTimeoutError(f"pipeline exceeded {self._timeout}s") from exc
        state = PipelineState.model_validate(raw)
        latency = (time.perf_counter() - start) * 1000
        self._remember(state)
        self._log(state, latency)
        return build_result(state, latency)

    async def stream(self, request_id: str, query: str, options: PipelineOptions) -> AsyncIterator[dict[str, Any]]:
        """Yield public events: start, intent, safety, complexity, analysis, plan, retrieval, reranking,
        evidence, bns_alert, token (real LLM deltas), citation, validation, complete | error."""
        start = time.perf_counter()
        options = options.model_copy(update={"streaming": True})
        state_data: dict[str, Any] = self._initial(request_id, query, options)
        yield {"type": "start", "request_id": request_id}
        try:
            async with asyncio.timeout(self._timeout):
                async for mode, payload in self._graph.astream(
                    state_data, stream_mode=["updates", "custom"], config={"recursion_limit": 40}
                ):
                    if mode == "custom":
                        yield payload
                        continue
                    for node, update in payload.items():
                        if not update:
                            continue
                        _merge(state_data, update)
                        event = _stage_event(node, update)
                        if event:
                            yield event
                        if node == "classify":
                            yield {"type": "analysis", **analysis_summary(state_data)}
                        if node in ("refuse", "small_talk", "insufficient") and update.get("answer"):
                            # Fixed (non-generated) message: delivered as one token event so token-
                            # concatenating clients render it; this is not simulated streaming.
                            yield {"type": "token", "content": update["answer"]}
        except TimeoutError:
            yield {"type": "error", "code": PipelineTimeoutError.code, "message": PipelineTimeoutError.public_message,
                   "request_id": request_id}
            return
        except AppError as exc:
            logger.warning("stream failed", extra={"error_category": exc.code, "error": str(exc)[:300]})
            yield {"type": "error", "code": exc.code, "message": exc.public_message, "request_id": request_id}
            return

        state = PipelineState.model_validate(state_data)
        latency = (time.perf_counter() - start) * 1000
        self._remember(state)
        self._log(state, latency)
        result = build_result(state, latency)
        if not self._diagnostics:
            result = trim_for_public(result)
        for citation in result.citations:
            yield {"type": "citation", **citation.model_dump(mode="json")}
        if result.metadata.output_validation is not None:
            v = result.metadata.output_validation
            yield {"type": "validation", "valid": v.valid, "warnings": v.warnings,
                   "invalid_citation_ids": v.invalid_citation_ids}
        yield {"type": "complete", "status": result_status(result),
               **result.model_dump(mode="json", exclude={"evidence"})}


_REDUCED = {"warnings", "errors"}


def _merge(state: dict[str, Any], update: dict[str, Any]) -> None:
    """Apply a node update to the locally tracked state, mirroring the graph's reducers."""
    for key, value in update.items():
        if key in _REDUCED:
            state[key] = list(state.get(key, [])) + list(value)
        elif key == "timings_ms":
            merged = dict(state.get(key, {}))
            for k, v in value.items():
                merged[k] = round(merged.get(k, 0.0) + v, 2)
            state[key] = merged
        else:
            state[key] = value
