"""Unit tests for each LangGraph node in isolation (state in -> partial update out)."""

from __future__ import annotations

import pytest

from app.container import Container
from app.core.exceptions import LLMProviderError
from app.domain.query import Complexity, Intent, SafetyDecision
from app.domain.retrieval import MappingType
from app.graph.builder import _after_answer, _after_classify, _after_evidence, _after_safety
from app.graph.nodes import PipelineNodes
from app.graph.state import PipelineMode, PipelineOptions, PipelineState, Route
from app.services.generation import INSUFFICIENT_EVIDENCE_ANSWER


def nodes(container: Container) -> PipelineNodes:
    return PipelineNodes(container.services)


def state(query: str, **options: object) -> PipelineState:
    return PipelineState(request_id="t", query=query, options=PipelineOptions(**options))


async def advance(n: PipelineNodes, s: PipelineState, *names: str) -> PipelineState:
    for name in names:
        update = await getattr(n, name)(s)
        data = s.model_dump()
        for key, value in update.items():
            if key in ("warnings", "errors"):
                data[key] = data[key] + list(value)
            elif key == "timings_ms":
                data[key] = {**data[key], **value}
            else:
                data[key] = value
        s = PipelineState.model_validate(data)
    return s


async def test_understand_node(container: Container) -> None:
    s = await advance(nodes(container), state("Explain u/s 420 IPC"), "understand")
    assert s.normalized_query == "Explain under Section 420 IPC"
    assert [(e.act, e.value) for e in s.entities if e.type.value == "section"] == [("IPC", "420")]
    assert s.intent and s.intent.intent == Intent.STATUTE_LOOKUP and "understand" in s.timings_ms


@pytest.mark.parametrize(("query", "route"), [("Will I win my case?", Route.REFUSE), ("hello", Route.SMALL_TALK),
                                              ("What is theft?", None)])
async def test_safety_node_and_router(container: Container, query: str, route: Route | None) -> None:
    s = await advance(nodes(container), state(query), "understand", "safety")
    assert s.route == route
    assert _after_safety(s) == {Route.REFUSE: "refuse", Route.SMALL_TALK: "small_talk"}.get(route, "classify")


async def test_refuse_node(container: Container) -> None:
    s = await advance(nodes(container), state("Will I win my case?"), "understand", "safety", "refuse")
    assert s.refused and "cannot predict" in (s.answer or "")
    assert s.safety and s.safety.decision == SafetyDecision.REFUSE


@pytest.mark.parametrize(("query", "complexity", "plan"), [
    ("What is Article 21?", Complexity.SIMPLE, "plan_simple"),
    ("Explain the difference between Article 14 and Article 21.", Complexity.MODERATE, "plan_moderate"),
    ("Compare IPC 420 and BNS 318 and explain how the change affects an accused after 2024", Complexity.COMPLEX,
     "plan_complex"),
])
async def test_classify_node_and_router(container: Container, query: str, complexity: Complexity, plan: str) -> None:
    s = await advance(nodes(container), state(query), "understand", "safety", "classify")
    assert s.complexity and s.complexity.complexity == complexity and s.profile
    assert _after_classify(s) == plan


async def test_plan_nodes(container: Container) -> None:
    n = nodes(container)
    simple = await advance(n, state("What is Article 21?"), "understand", "safety", "classify", "plan_simple")
    assert [q.subquery_id for q in simple.subqueries] == ["q0"] and simple.decomposition_method == "none"
    moderate = await advance(n, state("What is the BNS equivalent of Section 420 IPC?"),
                             "understand", "safety", "classify", "plan_moderate")
    assert moderate.decomposition_method == "expansion" and len(moderate.subqueries) > 1
    complex_ = await advance(n, state("Compare IPC 420 and BNS 318 and explain the impact after 2024", allow_llm=False),
                             "understand", "safety", "classify", "plan_complex")
    assert complex_.decomposition_method == "rule" and len(complex_.subqueries) > 2


async def test_retrieve_rerank_fuse_map_nodes(container: Container) -> None:
    s = await advance(nodes(container), state("What is the punishment under Section 420 IPC?"),
                      "understand", "safety", "classify", "plan_simple", "retrieve")
    assert s.retrieval_results and set(s.retrieval_source_counts) >= {"dense", "sparse", "metadata"}
    s = await advance(nodes(container), s, "rerank")
    assert s.reranked_results and s.reranker_used == "lexical"
    assert all(r.rerank_score is not None for r in s.reranked_results)
    s = await advance(nodes(container), s, "fuse")
    assert s.context and s.context.items and s.context.items[0].citation_id == "C1"
    s = await advance(nodes(container), s, "map_provisions")
    assert any(m.source_section == "420" and m.mapping_type == MappingType.EXACT for m in s.mappings)
    assert all(m.citation_id and m.citation_id.startswith("M") for m in s.mappings)


async def test_validate_evidence_node_and_router(container: Container) -> None:
    n = nodes(container)
    good = await advance(n, state("What is the punishment under Section 420 IPC?"), "understand", "safety",
                         "classify", "plan_simple", "retrieve", "rerank", "fuse", "map_provisions", "validate_evidence")
    assert good.evidence and good.evidence.sufficient and _after_evidence(good) == "generate"
    off = await advance(n, state("What is the law on space mining royalties?"), "understand", "safety",
                        "classify", "plan_simple", "retrieve", "rerank", "fuse", "map_provisions", "validate_evidence")
    assert off.evidence and not off.evidence.sufficient and _after_evidence(off) == "insufficient"
    off = await advance(n, off, "insufficient")
    assert off.answer == INSUFFICIENT_EVIDENCE_ANSWER
    search = await advance(n, state("Section 420 IPC", mode=PipelineMode.SEARCH), "understand", "safety", "classify",
                           "plan_simple", "retrieve", "rerank", "fuse", "map_provisions", "validate_evidence")
    assert _after_evidence(search) == "end"


async def test_generate_and_validate_answer_nodes(container: Container) -> None:
    s = await advance(nodes(container), state("What is the punishment under Section 420 IPC?"), "understand", "safety",
                      "classify", "plan_simple", "retrieve", "rerank", "fuse", "map_provisions", "validate_evidence",
                      "generate")
    assert s.generation and s.generation.provider == "fake" and "[C1]" in s.generation.text
    s = await advance(nodes(container), s, "validate_answer")
    assert s.output_validation and s.output_validation.valid and s.answer
    assert [c.citation_id for c in s.citations] == ["C1"] and _after_answer(s) == "end"


async def test_validate_answer_requests_bounded_regeneration(container: Container) -> None:
    s = await advance(nodes(container), state("What is the punishment under Section 420 IPC?"), "understand", "safety",
                      "classify", "plan_simple", "retrieve", "rerank", "fuse", "map_provisions", "validate_evidence")
    from app.domain.retrieval import GenerationResult

    s = s.model_copy(update={"generation": GenerationResult(text="Invented [C99].", provider="x", model="y")})
    retry = await advance(nodes(container), s, "validate_answer")
    assert retry.answer is None and retry.corrective_feedback and retry.regenerations == 1
    assert _after_answer(retry) == "generate"
    final = await advance(nodes(container), retry.model_copy(update={"regenerations": 1}), "validate_answer")
    assert final.answer is not None and "[C99]" not in final.answer and _after_answer(final) == "end"


async def test_generate_node_propagates_provider_failure(container: Container) -> None:
    s = await advance(nodes(container), state("What is the punishment under Section 420 IPC?"), "understand", "safety",
                      "classify", "plan_simple", "retrieve", "rerank", "fuse", "map_provisions", "validate_evidence")
    provider = container.llm.providers[0]
    provider._failures = [LLMProviderError("down")] * 3  # type: ignore[attr-defined]
    with pytest.raises(LLMProviderError):
        await advance(nodes(container), s, "generate")
