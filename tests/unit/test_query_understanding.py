from __future__ import annotations

import json

import pytest

from app.core.config import PROJECT_ROOT
from app.domain.query import Complexity, EntityType, Intent, SafetyDecision
from app.rag.query.complexity import ComplexityConfig, QueryComplexityClassifier
from app.rag.query.entities import extract_entities, provision_refs
from app.rag.query.intent import IntentDetector
from app.rag.query.normalizer import normalize_query
from app.services.safety import SafetyGuard
from app.services.session_memory import SessionMemory, SessionTurn, resolve_follow_up


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Explain Section 420 IPC", [("IPC", "420")]),
        ("What is s. 304A of the Indian Penal Code?", [("IPC", "304A")]),
        ("u/s 302 IPC", [("IPC", "302")]),
        ("IPC 302 vs BNS 103(1)", [("IPC", "302"), ("BNS", "103")]),
        ("Compare Sections 299 and 300 under the IPC", [("IPC", "299"), ("IPC", "300")]),
        ("420 IPC and 318 BNS", [("IPC", "420"), ("BNS", "318")]),
        ("Section 154 CrPC", [("CRPC", "154")]),
        ("Articles 14, 19 and 21", [("CONSTITUTION", "14"), ("CONSTITUTION", "19"), ("CONSTITUTION", "21")]),
    ],
)
def test_provision_extraction(query: str, expected: list[tuple[str, str]]) -> None:
    assert provision_refs(extract_entities(normalize_query(query))) == expected


def test_case_citations_extracted() -> None:
    entities = extract_entities("Maneka Gandhi v. Union of India, AIR 1978 SC 597")
    values = {e.value for e in entities if e.type == EntityType.CASE_CITATION}
    assert "Maneka Gandhi v. Union of India" in values and "AIR 1978 SC 597" in values


def test_no_entities_in_plain_question() -> None:
    assert extract_entities("punishment for murder") == []


def test_normalizer_expands_abbreviations() -> None:
    assert normalize_query("punishment  u/s 302 r/w sec. 34") == "punishment under Section 302 read with Section 34"


@pytest.mark.parametrize(
    ("query", "intent"),
    [
        ("hello", Intent.SMALL_TALK),
        ("What is the BNS equivalent of IPC 420?", Intent.PROVISION_MAPPING),
        ("Explain Section 420 IPC", Intent.STATUTE_LOOKUP),
        ("Which landmark judgments interpret Article 21?", Intent.CASE_LAW),
        ("How to file an FIR?", Intent.PROCEDURAL),
    ],
)
def test_intent_detection(query: str, intent: Intent) -> None:
    q = normalize_query(query)
    assert IntentDetector().detect(q, extract_entities(q)).intent == intent


def _classify(query: str):  # type: ignore[no-untyped-def]
    q = normalize_query(query)
    entities = extract_entities(q)
    return QueryComplexityClassifier().classify(q, entities, IntentDetector().detect(q, entities))


def test_simple_query_is_simple() -> None:
    result = _classify("What is the punishment for theft?")
    assert result.complexity == Complexity.SIMPLE
    assert not result.requires_decomposition


def test_comparison_across_codes_is_complex_with_reasons() -> None:
    result = _classify("Compare IPC 420 and BNS 318 and explain how the change affects an accused before and after 2024")
    assert result.complexity == Complexity.COMPLEX
    assert result.requires_decomposition and result.requires_multi_hop
    assert any("comparison" in r for r in result.reasons)
    assert {e.value for e in result.detected_entities} >= {"420", "318"}


def test_complexity_thresholds_are_configurable() -> None:
    strict = QueryComplexityClassifier(ComplexityConfig(moderate_threshold=0.1, complex_threshold=0.2))
    q = "Explain Article 21 and Article 14"
    assert strict.classify(q, extract_entities(q)).complexity == Complexity.COMPLEX


def test_safety_questionnaire_all_pass() -> None:
    guard = SafetyGuard()
    data = json.loads((PROJECT_ROOT / "evaluation" / "safety_questions.json").read_text(encoding="utf-8"))
    for q in data["questions"]:
        decision = guard.check(normalize_query(q["query"])).decision
        got = "refuse" if decision == SafetyDecision.REFUSE else "allow"
        assert got == q["expected"], q["query"]


def test_safety_redirect_matches_category() -> None:
    guard = SafetyGuard()
    result = guard.check("Will I win my case?")
    assert "cannot predict" in guard.redirect_message(result)


def test_follow_up_inherits_previous_provisions() -> None:
    memory = SessionMemory(max_turns=2)
    previous = extract_entities("Explain Section 420 IPC")
    memory.add("u:s1", SessionTurn(query="Explain Section 420 IPC", entities=previous))
    resolution = resolve_follow_up("What is its punishment?", [], memory.history("u:s1"))
    assert resolution.is_follow_up
    assert provision_refs(resolution.inherited_entities) == [("IPC", "420")]
    assert "Section 420" in resolution.retrieval_query


def test_session_memory_is_bounded() -> None:
    memory = SessionMemory(max_turns=2, max_sessions=10)
    for i in range(5):
        memory.add("k", SessionTurn(query=f"q{i}"))
    assert [t.query for t in memory.history("k")] == ["q3", "q4"]
    for i in range(20):
        memory.add(f"s{i}", SessionTurn(query="x"))
    assert memory.session_count <= 10
