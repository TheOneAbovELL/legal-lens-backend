"""Development diagnostics: verify each backend component in isolation.

All checks are read-only (no ingestion, no writes). The LLM check makes one minimal request and
only runs when explicitly called. Nothing here returns credentials.
"""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

from app.core.exceptions import AppError
from app.domain.query import SafetyDecision
from app.providers.llm.base import ChatMessage, LLMRequest
from app.rag.query.entities import extract_entities
from app.rag.query.normalizer import normalize_query
from app.schemas.system import (
    ConfigSummary,
    EmbeddingDiagnostics,
    LLMDiagnostics,
    QdrantDiagnostics,
    RouteDiagnostics,
)

if TYPE_CHECKING:
    from app.container import Container

PROBE_TEXT = "Legal Lens embedding self-test: right to life and personal liberty under Article 21."


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


async def check_qdrant(c: Container) -> QdrantDiagnostics:
    start = time.perf_counter()
    base = {"mode": c.store.mode, "target": c.store.target, "collection": c.store.collection,
            "expected_dimension": c.settings.embedding_dimension, "sparse_enabled": c.store.sparse_enabled}
    try:
        info = await c.store.describe_collection()
    except AppError as exc:
        return QdrantDiagnostics(reachable=False, collection_exists=False, latency_ms=_ms(start),
                                 error=exc.public_message, **base)
    if not info["exists"]:
        return QdrantDiagnostics(reachable=True, collection_exists=False, latency_ms=_ms(start),
                                 error="collection missing; run scripts/ingest.py", **base)
    test_ok, hits = None, None
    if info.get("dimension"):
        probe = [0.0] * int(info["dimension"])
        probe[0] = 1.0  # unit vector: valid for cosine, independent of the embedding model
        try:
            hits = len(await c.store.search_dense(probe, None, 3))
            test_ok = True
        except AppError:
            test_ok = False
    profiles = await c.store.available_profiles()
    return QdrantDiagnostics(
        reachable=True, collection_exists=True, points=info.get("points"), dense_vector=info.get("dense_vector"),
        vector_dimension=info.get("dimension"), distance=info.get("distance"),
        sparse_vector=", ".join(info.get("sparse_vectors") or []) or None,
        indexed_chunk_profiles=profiles, test_query_ok=test_ok, test_query_hits=hits, latency_ms=_ms(start),
        error=None if info.get("dimension") == c.settings.embedding_dimension else "dimension mismatch", **base,
    )


async def check_embedding(c: Container) -> EmbeddingDiagnostics:
    start = time.perf_counter()
    base = {"model": c.embedder.model_name, "model_version": c.embedder.model_version,
            "expected_dimension": c.embedder.dimension}
    try:
        vector = await c.embedder.embed_documents([PROBE_TEXT])
    except AppError as exc:
        return EmbeddingDiagnostics(ok=False, loaded=c.embedder.is_ready, latency_ms=_ms(start),
                                    error=f"{exc.code}: {str(exc)[:200]}", **base)
    v = vector[0]
    finite = all(math.isfinite(x) for x in v)
    norm = math.sqrt(sum(x * x for x in v)) if finite else None
    non_zero = bool(norm)
    normalized = norm is not None and abs(norm - 1.0) < 1e-3
    ok = finite and non_zero and len(v) == c.embedder.dimension and normalized
    return EmbeddingDiagnostics(
        ok=ok, loaded=c.embedder.is_ready, dimension=len(v), finite=finite, non_zero=non_zero,
        l2_norm=round(norm, 6) if norm is not None else None, normalized=normalized, latency_ms=_ms(start),
        error=None if ok else "embedding failed validation", **base,
    )


async def check_llm(c: Container, prompt: str, max_tokens: int) -> LLMDiagnostics:
    start = time.perf_counter()
    configured = [f"{p.name}:{p.model}" for p in c.llm.providers if p.configured]
    if not configured:
        return LLMDiagnostics(ok=False, configured_providers=[], latency_ms=0.0,
                              error="no LLM provider credentials configured (LLM_API_KEY / GROQ_API_KEY)")
    try:
        response = await c.llm.complete(LLMRequest(
            messages=[ChatMessage(role="user", content=prompt)], temperature=0.0, max_tokens=max_tokens,
            timeout=min(c.settings.llm_timeout, 20.0),
        ))
    except AppError as exc:
        return LLMDiagnostics(ok=False, configured_providers=configured, latency_ms=_ms(start),
                              error=f"{exc.code}: {exc.public_message}")
    return LLMDiagnostics(
        ok=bool(response.text.strip()), configured_providers=configured, provider=response.provider,
        model=response.model, attempts=response.attempts, response_preview=response.text.strip()[:80],
        total_tokens=response.usage.total_tokens, latency_ms=_ms(start),
        error=None if response.text.strip() else "empty response",
    )


async def check_route(c: Container, query: str, use_llm: bool) -> RouteDiagnostics:
    """Run the deterministic front half of the graph (no retrieval, no generation)."""
    s = c.services
    normalized = normalize_query(query)
    entities = extract_entities(normalized)
    intent = s.intent_detector.detect(normalized, entities)
    safety = s.safety_guard.check(normalized)
    result = RouteDiagnostics(query=query, normalized_query=normalized, entities=[e.raw for e in entities],
                              intent=intent, safety=safety, would_refuse=safety.decision == SafetyDecision.REFUSE)
    if result.would_refuse:
        result.route = "refuse"
        return result
    complexity = s.complexity_classifier.classify(normalized, entities, intent)
    profile = s.profile_selector.select(complexity, intent).profile
    if profile.decomposition and s.decomposition_enabled:
        route = "complex"
        plan = await s.decomposer.decompose(normalized, entities, allow_llm=use_llm)
        subqueries, method = plan.subqueries, plan.method
    elif profile.query_expansion:
        route, method = "moderate", "expansion"
        subqueries = s.expander.expand(normalized, entities)
    else:
        from app.domain.query import SubQuery

        route, method = "simple", "none"
        subqueries = [SubQuery(subquery_id="q0", query=normalized, purpose="original question", priority=0)]
    result.complexity, result.route = complexity, route
    result.retrieval_profile, result.profile_selection = profile.name, profile.selection_reasons
    result.sources, result.reranker = profile.sources, profile.reranker
    result.decomposition_method, result.subqueries = method, subqueries
    return result


def config_summary(c: Container) -> ConfigSummary:
    st = c.settings
    return ConfigSummary(
        environment=st.app_env.value, version=st.app_version, diagnostics_enabled=st.diagnostics,
        auth_required=st.auth_required, registration_enabled=st.auth_allow_registration,
        rate_limit=f"{st.rate_limit_requests}/{st.rate_limit_window_seconds}s" if st.rate_limit_enabled else "disabled",
        vector_store=c.store.describe(), embedding_model=st.embedding_model, embedding_dimension=st.embedding_dimension,
        reranker_model=st.reranker_model, llm_targets=[f"{p}:{m}" for p, m in st.llm_targets],
        llm_api_key_configured=st.llm_api_key is not None, knowledge_graph_enabled=st.graph_enabled,
        complexity_routing_enabled=st.complexity_routing_enabled,
        decomposition=("llm+rules" if st.decomposition_use_llm else "rules") if st.query_decomposition_enabled else "disabled",
        default_chunk_profile=st.chunking_default_profile, adaptive_selection_mode=st.adaptive_selection_mode,
        session_memory_enabled=st.session_memory_enabled,
    )
