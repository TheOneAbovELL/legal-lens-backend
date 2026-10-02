"""Graph routing and end-to-end pipeline behaviour (fake LLM + in-memory Qdrant)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.container import Container
from app.core.exceptions import LLMProviderError
from app.graph.state import PipelineMode, PipelineOptions
from app.services.generation import INSUFFICIENT_EVIDENCE_ANSWER
from tests.conftest import ingest_corpus, make_container, make_settings
from tests.fakes import ScriptedLLM


async def run(container: Container, query: str, **opts):  # type: ignore[no-untyped-def]
    return await container.pipeline.run("test-req", query, PipelineOptions(**opts))


async def test_simple_route(container: Container) -> None:
    result = await run(container, "What is the punishment under Section 420 IPC?")
    meta = result.metadata
    assert meta.route == "simple" and meta.retrieval_profile == "FAST" and meta.decomposition_method == "none"
    assert result.citations and result.citations[0].section == "420"
    assert any(m.source_section == "420" and m.target_sections == ["318(4)"] for m in result.mappings)
    assert meta.provider == "fake" and meta.output_validation and meta.output_validation.valid
    assert result.disclaimer


async def test_moderate_route_uses_expansion(container: Container) -> None:
    result = await run(container, "What is the BNS equivalent of Section 420 IPC?")
    assert result.metadata.route == "moderate"
    assert result.metadata.decomposition_method == "expansion" and len(result.metadata.subqueries) > 1


async def test_complex_route_decomposes(tmp_path: Path) -> None:
    plan = json.dumps({"subqueries": [{"query": "IPC 420 cheating", "purpose": "old"}, {"query": "BNS 318", "purpose": "new"}]})
    llm = ScriptedLLM(["IPC 420 and BNS 318 both punish cheating [C1]."], json_answer=plan)
    c = make_container(make_settings(tmp_path), llm)
    await c.startup()
    await ingest_corpus(c)
    try:
        result = await run(c, "Compare IPC 420 and BNS 318 and explain how the change affects an accused after 2024")
        meta = result.metadata
        assert meta.route == "complex" and meta.retrieval_profile == "DEEP" and meta.decomposition_method == "llm"
        assert 2 < len(meta.subqueries) <= c.settings.decomposition_max_subqueries
        assert {"420", "318"} <= {e.metadata.section for e in result.evidence}
    finally:
        await c.shutdown()


async def test_safety_refusal_short_circuits(container: Container, llm: ScriptedLLM) -> None:
    result = await run(container, "Will I win my cheating case?")
    assert result.refused and result.metadata.route == "refuse"
    assert result.metadata.candidates == 0 and not llm.requests  # no retrieval, no LLM
    assert result.citations == []


async def test_small_talk_skips_retrieval(container: Container, llm: ScriptedLLM) -> None:
    result = await run(container, "hello")
    assert result.metadata.route == "small_talk" and not llm.requests


async def test_off_corpus_question_is_not_answered(container: Container, llm: ScriptedLLM) -> None:
    result = await run(container, "What is the law on space mining royalties?")
    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert not llm.requests and result.citations == []


async def test_search_mode_never_calls_llm(container: Container, llm: ScriptedLLM) -> None:
    result = await run(container, "Compare IPC 420 and BNS 318 and explain the impact of the change",
                       mode=PipelineMode.SEARCH, allow_llm=False, top_k=5)
    assert result.answer is None and result.evidence and not llm.requests
    assert result.metadata.decomposition_method in ("rule", "expansion", "none")


async def test_invalid_output_triggers_bounded_regeneration(tmp_path: Path) -> None:
    llm = ScriptedLLM(["Wrong, see Section 999 [C42].", "Corrected answer about cheating [C1]."])
    c = make_container(make_settings(tmp_path), llm)
    await c.startup()
    await ingest_corpus(c)
    try:
        result = await run(c, "What is the punishment under Section 420 IPC?")
        assert result.answer == "Corrected answer about cheating [C1]."
        assert result.metadata.output_validation and result.metadata.output_validation.regenerated
        assert len(llm.requests) == 2
        corrective = llm.requests[1].messages[-1].content
        assert "PREVIOUS DRAFT WAS REJECTED" in corrective
    finally:
        await c.shutdown()


async def test_persistently_invalid_output_is_sanitised(tmp_path: Path) -> None:
    llm = ScriptedLLM(["Bad [C42] answer about Section 420."])
    c = make_container(make_settings(tmp_path), llm)
    await c.startup()
    await ingest_corpus(c)
    try:
        result = await run(c, "What is the punishment under Section 420 IPC?")
        assert "[C42]" not in (result.answer or "")
        assert any("unknown evidence IDs" in w for w in result.warnings)
        assert len(llm.requests) == 2  # 1 regeneration max
    finally:
        await c.shutdown()


async def test_llm_failure_surfaces_structured_error(tmp_path: Path) -> None:
    failing = ScriptedLLM(failures=[LLMProviderError("down", retryable=False)] * 5)
    c = make_container(make_settings(tmp_path), failing)
    await c.startup()
    await ingest_corpus(c)
    try:
        with pytest.raises(LLMProviderError):
            await run(c, "What is the punishment under Section 420 IPC?")
    finally:
        await c.shutdown()


async def test_session_memory_resolves_follow_up(container: Container) -> None:
    await run(container, "Explain Section 420 IPC", session_key="u:s1")
    follow = await run(container, "What is its punishment?", session_key="u:s1")
    assert follow.metadata.follow_up
    assert any(e.metadata.section == "420" for e in follow.evidence)
    other = await run(container, "What is its punishment?", session_key="u:s2")
    assert not other.metadata.follow_up  # sessions are isolated


async def test_streaming_emits_real_tokens_and_done(container: Container) -> None:
    events = [e async for e in container.pipeline.stream("r", "Explain Section 420 IPC", PipelineOptions())]
    types = [e["type"] for e in events]
    assert types[0] == "start" and types[-1] == "complete"
    for stage in ("intent", "safety", "complexity", "plan", "retrieval", "evidence"):
        assert stage in types
    tokens = [e["content"] for e in events if e["type"] == "token"]
    assert len(tokens) > 3  # provider deltas, not one blob
    done = events[-1]
    assert done["answer"] == "".join(tokens).strip()
    assert "citation" in types and "validation" in types


async def test_streaming_reports_errors_as_events(tmp_path: Path) -> None:
    c = make_container(make_settings(tmp_path), ScriptedLLM(failures=[LLMProviderError("down")] * 5))
    await c.startup()
    await ingest_corpus(c)
    try:
        events = [e async for e in c.pipeline.stream("r", "Explain Section 420 IPC", PipelineOptions())]
        assert events[-1]["type"] == "error" and events[-1]["code"] == "llm_provider_error"
        assert "down" not in events[-1]["message"]  # internal detail not leaked
    finally:
        await c.shutdown()


async def test_profile_override_and_disabled_routing(tmp_path: Path) -> None:
    c = make_container(make_settings(tmp_path, complexity_routing_enabled=False))
    await c.startup()
    await ingest_corpus(c)
    try:
        r = await run(c, "What is the punishment for theft?")
        assert r.metadata.complexity and r.metadata.complexity.complexity.value == "MODERATE"
        forced = await run(c, "What is the punishment for theft?", profile_override="FAST")
        assert forced.metadata.retrieval_profile == "FAST"
    finally:
        await c.shutdown()
