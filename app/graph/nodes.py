"""LangGraph nodes. Each node is a thin adapter: it calls a service and returns a partial state
update (plus timing). No retrieval, prompting or scoring logic lives here."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from langgraph.config import get_stream_writer

from app.core.exceptions import LLMProviderError
from app.domain.acts import act_display_name
from app.domain.query import Complexity, ComplexityResult, EntityType, Intent, SafetyDecision, SubQuery
from app.domain.retrieval import (
    EvidenceValidation,
    GenerationResult,
    MappingType,
    RetrievalFilters,
    TokenUsage,
)
from app.graph.state import PipelineError, PipelineMode, PipelineState, Route
from app.providers.llm.router import StreamOrigin
from app.rag.fusion import ContextBudget, ContextBuilder
from app.rag.profiles import RetrievalProfileSelector
from app.rag.query.complexity import QueryComplexityClassifier
from app.rag.query.decomposition import QueryDecomposer
from app.rag.query.entities import extract_entities, provision_refs
from app.rag.query.expansion import QueryExpander
from app.rag.query.intent import IntentDetector
from app.rag.query.normalizer import normalize_query
from app.rag.reranking import RerankerSet
from app.rag.retrieval.hybrid import HybridRetriever
from app.rag.sparse import lexical_terms
from app.services.generation import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    SMALL_TALK_ANSWER,
    AnswerGenerator,
    build_messages,
    mapping_ids,
    normalize_citations,
    strip_citations,
    validate_output,
)
from app.services.legal_mapping import LegalProvisionMapper, base_section
from app.services.safety import SafetyGuard
from app.services.session_memory import SessionMemory, resolve_follow_up

MAX_MAPPINGS = 6
MAPPING_EVIDENCE_ITEMS = 3  # only the top evidence items contribute provision alerts


@dataclass
class PipelineServices:
    intent_detector: IntentDetector
    safety_guard: SafetyGuard
    complexity_classifier: QueryComplexityClassifier
    profile_selector: RetrievalProfileSelector
    expander: QueryExpander
    decomposer: QueryDecomposer
    retriever: HybridRetriever
    rerankers: RerankerSet
    context_builder: ContextBuilder
    mapper: LegalProvisionMapper
    generator: AnswerGenerator
    memory: SessionMemory | None
    ceiling: ContextBudget
    complexity_routing_enabled: bool = True
    decomposition_enabled: bool = True
    max_regenerations: int = 1
    evidence_min_term_coverage: float = 0.34
    evidence_min_dense_score: float = 0.6


def _stream_writer():  # type: ignore[no-untyped-def]
    """LangGraph's custom-stream writer, or a no-op when the node runs outside a graph (unit tests)."""
    try:
        return get_stream_writer()
    except RuntimeError:
        return lambda _event: None


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


class PipelineNodes:
    def __init__(self, services: PipelineServices) -> None:
        self.s = services

    # ------------------------------------------------------------ understand
    async def understand(self, state: PipelineState) -> dict[str, Any]:
        t = time.perf_counter()
        normalized = normalize_query(state.query)
        entities = extract_entities(normalized)
        history = []
        if self.s.memory is not None and state.options.session_key:
            history = self.s.memory.history(state.options.session_key)
        follow = resolve_follow_up(normalized, entities, history)
        merged = entities + [e for e in follow.inherited_entities if e.key not in {x.key for x in entities}]
        intent = self.s.intent_detector.detect(normalized, merged)
        return {
            "normalized_query": normalized,
            "retrieval_query": follow.retrieval_query,
            "entities": merged,
            "history": history,
            "follow_up": follow.is_follow_up,
            "intent": intent,
            "timings_ms": {"understand": _ms(t)},
        }

    # ---------------------------------------------------------------- safety
    async def safety(self, state: PipelineState) -> dict[str, Any]:
        t = time.perf_counter()
        result = self.s.safety_guard.check(state.normalized_query)
        update: dict[str, Any] = {"safety": result, "timings_ms": {"safety": _ms(t)}}
        if result.decision == SafetyDecision.REFUSE:
            update["route"] = Route.REFUSE
        elif state.intent and state.intent.intent == Intent.SMALL_TALK:
            update["route"] = Route.SMALL_TALK
        if result.jurisdiction_note:
            update["warnings"] = [result.jurisdiction_note]
        return update

    async def refuse(self, state: PipelineState) -> dict[str, Any]:
        assert state.safety is not None
        return {"answer": self.s.safety_guard.redirect_message(state.safety), "refused": True}

    async def small_talk(self, state: PipelineState) -> dict[str, Any]:
        return {"answer": SMALL_TALK_ANSWER}

    # -------------------------------------------------------------- classify
    async def classify(self, state: PipelineState) -> dict[str, Any]:
        t = time.perf_counter()
        if self.s.complexity_routing_enabled:
            complexity = self.s.complexity_classifier.classify(state.normalized_query, state.entities, state.intent)
        else:
            complexity = ComplexityResult(
                complexity=Complexity.MODERATE, confidence=1.0, score=0.0,
                reasons=["complexity routing disabled; fixed MODERATE path"], detected_entities=state.entities,
            )
        filters = state.options.filters
        selection = self.s.profile_selector.select(
            complexity, state.intent, override=state.options.profile_override,
            document_types=filters.document_types if filters else None,
        )
        profile = selection.profile
        if state.options.top_k:
            profile.top_k = state.options.top_k
            profile.candidate_k = max(profile.candidate_k, state.options.top_k)
        if profile.decomposition and self.s.decomposition_enabled:
            route = Route.COMPLEX
        elif profile.query_expansion:
            route = Route.MODERATE
        else:
            route = Route.SIMPLE
        return {
            "complexity": complexity, "profile": profile, "profile_mode": selection.mode, "route": route,
            "timings_ms": {"classify": _ms(t)},
        }

    # ------------------------------------------------------------- planning
    async def plan_simple(self, state: PipelineState) -> dict[str, Any]:
        return {
            "subqueries": [SubQuery(subquery_id="q0", query=state.retrieval_query, purpose="original question", priority=0)],
            "decomposition_method": "none",
        }

    async def plan_moderate(self, state: PipelineState) -> dict[str, Any]:
        t = time.perf_counter()
        subqueries = self.s.expander.expand(state.retrieval_query, state.entities)
        return {"subqueries": subqueries, "decomposition_method": "expansion", "timings_ms": {"plan": _ms(t)}}

    async def plan_complex(self, state: PipelineState) -> dict[str, Any]:
        t = time.perf_counter()
        allow_llm = state.options.allow_llm and state.options.mode == PipelineMode.ANSWER
        result = await self.s.decomposer.decompose(state.retrieval_query, state.entities, allow_llm=allow_llm)
        return {
            "subqueries": result.subqueries, "decomposition_method": result.method, "warnings": result.warnings,
            "timings_ms": {"decomposition": _ms(t)},
        }

    # ------------------------------------------------------------ retrieval
    async def retrieve(self, state: PipelineState) -> dict[str, Any]:
        t = time.perf_counter()
        assert state.profile is not None
        profile = state.profile
        base = state.options.filters or RetrievalFilters()
        filters = base.merged(chunk_profiles=base.chunk_profiles or profile.chunk_profiles)
        result = await self.s.retriever.retrieve(
            state.subqueries, state.entities, filters=filters, candidate_k=profile.candidate_k,
            sources=profile.sources, weights=profile.source_weights,
        )
        errors = [
            PipelineError(stage="retrieval", category="source_failure", message=f"{e.source}: {e.error}")
            for e in result.errors
        ]
        warnings = [f"retrieval source unavailable: {s}" for s in sorted({e.source for e in result.errors})]
        timings = {"retrieval": _ms(t)}
        timings.update({f"retrieval.{k}": v for k, v in result.timings_ms.items()})
        return {
            "retrieval_results": result.candidates, "retrieval_source_counts": result.source_counts,
            "errors": errors, "warnings": warnings, "timings_ms": timings,
        }

    async def rerank(self, state: PipelineState) -> dict[str, Any]:
        t = time.perf_counter()
        assert state.profile is not None
        profile = state.profile
        # Each candidate is scored against the sub-query that retrieved it (cross-encoder cost is
        # the same as scoring against the original question, but coverage is preserved).
        by_subquery: dict[str, list] = {}
        texts = {sq.subquery_id: sq.query for sq in state.subqueries}
        priorities = {sq.subquery_id: sq.priority for sq in state.subqueries}
        for candidate in state.retrieval_results:
            key = candidate.primary_subquery(priorities)
            if key not in texts:
                key = state.subqueries[0].subquery_id
            by_subquery.setdefault(key, []).append(candidate)
        reranked = []
        used: set[str] = set()
        warnings: list[str] = []
        for sid, group in by_subquery.items():
            result, used_name, warning = await self.s.rerankers.rerank(
                profile.reranker, texts.get(sid, state.retrieval_query), group, state.entities, profile.top_k
            )
            reranked.extend(result)
            used.add(used_name)
            if warning and warning not in warnings:
                warnings.append(warning)
        reranked.sort(key=lambda c: c.final_score, reverse=True)
        return {
            "reranked_results": reranked, "reranker_used": ",".join(sorted(used)) or profile.reranker,
            "warnings": warnings, "timings_ms": {"rerank": _ms(t)},
        }

    async def fuse(self, state: PipelineState) -> dict[str, Any]:
        t = time.perf_counter()
        assert state.profile is not None
        p, ceiling = state.profile, self.s.ceiling
        budget = ContextBudget(
            max_context_tokens=min(p.max_context_tokens, ceiling.max_context_tokens),
            max_chunks=min(p.max_chunks, ceiling.max_chunks),
            max_chunks_per_document=min(p.max_chunks_per_document, ceiling.max_chunks_per_document),
            max_evidence_per_subquery=min(p.max_evidence_per_subquery, ceiling.max_evidence_per_subquery),
            min_relative_relevance=ceiling.min_relative_relevance,
        )
        if state.options.mode == PipelineMode.SEARCH:
            # Search results are not sent to an LLM: no token budget, the caller's top_k decides.
            budget = budget.model_copy(update={
                "max_context_tokens": 1_000_000, "max_chunks": p.top_k,
                "max_chunks_per_document": p.top_k, "max_evidence_per_subquery": p.top_k,
            })
        context = self.s.context_builder.build(state.reranked_results, state.subqueries, budget)
        return {"context": context, "timings_ms": {"context_fusion": _ms(t)}}

    async def map_provisions(self, state: PipelineState) -> dict[str, Any]:
        t = time.perf_counter()
        refs = [r for r in provision_refs(state.entities) if self.s.mapper.supports(r[0])]
        if state.context:
            # Alerts come from provisions the user named, exact-match evidence, and only the single
            # best-scored other passage — not from every neighbour that made it into the context.
            pinned = [i for i in state.context.items if {"metadata", "graph"} & set(i.chunk.scores)]
            others = sorted((i for i in state.context.items if i not in pinned),
                            key=lambda i: i.chunk.final_score, reverse=True)
            top = (pinned + others[:1])[:MAPPING_EVIDENCE_ITEMS] if not pinned else pinned[:MAPPING_EVIDENCE_ITEMS]
            for item in top:
                md = item.chunk.metadata
                if md.act and md.section and self.s.mapper.supports(md.act) and (md.act, md.section) not in refs:
                    refs.append((md.act, md.section))
        mappings = list(await asyncio.gather(*(self.s.mapper.map(act, section) for act, section in refs[:MAX_MAPPINGS])))
        # Keep evidence-derived "unknown" mappings out of the prompt; only the user's own provisions
        # are reported as unknown so the answer can say so explicitly.
        asked = set(provision_refs(state.entities))
        mappings = [m for m in mappings if m.mapping_type != MappingType.UNKNOWN or (m.source_act, m.source_section) in asked]
        # BNS 101 -> IPC 300 duplicates IPC 300 -> BNS 101: keep one alert per provision pair.
        seen_pairs: set[frozenset[tuple[str, str]]] = set()
        unique = []
        for m in mappings:
            pairs = {frozenset({(m.source_act, base_section(m.source_section)), (m.target_act, base_section(t))})
                     for t in m.target_sections}
            if pairs and pairs <= seen_pairs:
                continue
            seen_pairs |= pairs
            unique.append(m)
        mappings = unique
        return {"mappings": mapping_ids(mappings), "timings_ms": {"provision_mapping": _ms(t)}}

    async def validate_evidence(self, state: PipelineState) -> dict[str, Any]:
        context = state.context
        items = context.items if context else []
        asked = set(provision_refs(state.entities))
        # Only mappings for provisions the user named can stand in for missing document evidence.
        informative_maps = [
            m for m in state.mappings
            if m.mapping_type != MappingType.UNKNOWN and (m.source_act, m.source_section) in asked
        ]
        covered = {sid for item in items for sid in item.chunk.subquery_ids}
        uncovered = [sq.query for sq in state.subqueries if sq.priority > 0 and sq.subquery_id not in covered]
        present = {(i.chunk.metadata.act, i.chunk.metadata.section) for i in items}
        missing = []
        for e in state.entities:
            if e.type in (EntityType.SECTION, EntityType.ARTICLE) and e.act and (e.act, e.value) not in present:
                missing.append(f"{act_display_name(e.act)} {'Article' if e.type == EntityType.ARTICLE else 'Section'} {e.value}")
        warnings = []
        if missing:
            warnings.append("the indexed sources do not contain: " + ", ".join(missing))
        if uncovered:
            warnings.append(f"{len(uncovered)} sub-question(s) found no supporting evidence")
        relevant = self._relevance_gate(state, items)
        if items and not relevant:
            warnings.append("retrieved passages do not appear to address the question")
        evidence = EvidenceValidation(
            sufficient=(bool(items) and relevant) or bool(informative_maps),
            evidence_count=len(items),
            uncovered_subqueries=uncovered,
            missing_provisions=missing,
            warnings=warnings,
        )
        return {"evidence": evidence, "warnings": warnings}

    def _relevance_gate(self, state: PipelineState, items: list) -> bool:
        """Absolute relevance check so off-corpus questions are not answered from noise."""
        if not items:
            return False
        if any({"metadata", "graph"} & set(i.chunk.scores) for i in items):
            return True
        terms = set(lexical_terms(state.retrieval_query or state.normalized_query))
        evidence_terms: set[str] = set()
        for item in items:
            evidence_terms.update(lexical_terms(f"{item.chunk.context_header} {item.chunk.content}"))
        coverage = len(terms & evidence_terms) / len(terms) if terms else 1.0
        best_dense = max((i.chunk.scores.get("dense", 0.0) for i in items), default=0.0)
        return coverage >= self.s.evidence_min_term_coverage or best_dense >= self.s.evidence_min_dense_score

    async def insufficient(self, state: PipelineState) -> dict[str, Any]:
        asked = set(provision_refs(state.entities))
        mappings = [m for m in state.mappings if (m.source_act, m.source_section) in asked]
        return {"answer": INSUFFICIENT_EVIDENCE_ANSWER, "mappings": mappings}

    # ------------------------------------------------------------ generation
    async def generate(self, state: PipelineState) -> dict[str, Any]:
        t = time.perf_counter()
        assert state.context is not None and state.evidence is not None
        notes = list(state.evidence.warnings)
        if state.safety and state.safety.jurisdiction_note:
            notes.append(state.safety.jurisdiction_note)
        messages = build_messages(
            question=state.normalized_query,
            context=state.context,
            mappings=state.mappings,
            notes=notes,
            history=state.history,
            role=state.options.user_role,
            corrective_feedback=state.corrective_feedback,
        )
        writer = _stream_writer()
        parts: list[str] = []
        usage = TokenUsage()
        provider = model = "unknown"
        attempts = 1
        async for chunk in self.s.generator.stream(messages):
            if isinstance(chunk, StreamOrigin):
                provider, model, attempts = chunk.provider, chunk.model, chunk.attempts
                continue
            if chunk.usage is not None:
                usage = chunk.usage
            if chunk.delta:
                parts.append(chunk.delta)
                writer({"type": "token", "content": normalize_citations(chunk.delta), "attempt": state.regenerations})
        text = "".join(parts).strip()
        if not text:
            raise LLMProviderError("LLM returned an empty answer", provider=provider)
        return {
            "generation": GenerationResult(text=text, provider=provider, model=model, usage=usage, attempts=attempts),
            "timings_ms": {"generation": _ms(t)},
        }

    async def validate_answer(self, state: PipelineState) -> dict[str, Any]:
        assert state.generation is not None and state.context is not None
        validation = validate_output(state.generation.text, state.context, state.mappings, state.entities)
        can_retry = (
            not validation.valid
            and not state.options.streaming
            and state.regenerations < self.s.max_regenerations
        )
        if can_retry:
            feedback = "; ".join(validation.warnings[:2])
            return {"output_validation": validation, "corrective_feedback": feedback,
                    "regenerations": state.regenerations + 1}
        answer = strip_citations(normalize_citations(state.generation.text), set(validation.invalid_citation_ids))
        validation.regenerated = state.regenerations > 0
        cited = set(validation.cited_ids)
        # Only evidence the answer actually cites is returned as citations (never a blanket list).
        citations = [c for c in state.context.citations() if c.citation_id in cited]
        return {
            "output_validation": validation, "answer": answer, "citations": citations,
            "warnings": validation.warnings, "corrective_feedback": None,
        }
