from __future__ import annotations

from pathlib import Path

from app.container import Container
from app.domain.retrieval import BuiltContext
from app.providers.llm.router import LLMRouter
from app.rag.chunking.base import ChunkingProfile
from app.rag.query.decomposition import QueryDecomposer, RuleBasedDecomposer
from app.rag.query.entities import extract_entities
from app.rag.query.expansion import QueryExpander
from app.services.generation import cited_ids, strip_citations, validate_output
from tests.conftest import CORPUS
from tests.fakes import ScriptedLLM
from tests.rag.test_retrieval import _chunk


def _context() -> BuiltContext:
    from app.domain.query import SubQuery
    from app.rag.fusion import ContextBudget, ContextBuilder

    chunk = _chunk("a", "420. Cheating — punished with imprisonment up to seven years", 0.9, section="420")
    return ContextBuilder().build([chunk], [SubQuery(subquery_id="q0", query="q", purpose="p")], ContextBudget())


def test_citation_parsing_and_stripping() -> None:
    text = "Fact one [C1]. Fact two [C1, C9]. Mapping [M1]."
    assert cited_ids(text) == ["C1", "C9", "M1"]
    assert strip_citations(text, {"C9"}) == "Fact one [C1]. Fact two [C1]. Mapping [M1]."


def test_output_validation_flags_fabricated_ids_and_provisions() -> None:
    ctx = _context()
    good = validate_output("Section 420 is punished with seven years [C1].", ctx, [], [])
    assert good.valid and good.cited_ids == ["C1"]
    fake_id = validate_output("Something [C7].", ctx, [], [])
    assert not fake_id.valid and fake_id.invalid_citation_ids == ["C7"]
    fake_section = validate_output("Also see Section 511 IPC [C1].", ctx, [], [])
    assert not fake_section.valid and fake_section.unsupported_references
    fake_case = validate_output("As held in Kesavananda Bharati v. State of Kerala [C1].", ctx, [], [])
    assert not fake_case.valid


def test_rule_based_decomposer_is_bounded_and_deduplicated(container: Container) -> None:
    decomposer = RuleBasedDecomposer(container.mapper, max_subqueries=4)
    q = "Compare IPC 420 and BNS 318? What is the punishment? What is the punishment?"
    subqueries = decomposer.decompose(q, extract_entities(q))
    assert 1 < len(subqueries) <= 4
    assert subqueries[0].query == q and subqueries[0].priority == 0
    assert len({s.query.lower() for s in subqueries}) == len(subqueries)


async def test_llm_decomposer_falls_back_on_bad_json(container: Container) -> None:
    llm = LLMRouter([ScriptedLLM(json_answer="{not json")], max_retries=0, backoff=0)
    decomposer = QueryDecomposer(rule_based=RuleBasedDecomposer(container.mapper, 5), llm=llm, use_llm=True,
                                 max_subqueries=5, timeout=2, max_tokens=100)
    result = await decomposer.decompose("Compare IPC 302 and BNS 103", extract_entities("Compare IPC 302 and BNS 103"))
    assert result.method == "rule_fallback" and result.warnings


async def test_llm_decomposer_valid_plan_keeps_original(container: Container) -> None:
    plan = '{"subqueries": [{"query": "IPC section 302 punishment", "purpose": "old"}, {"query": "BNS 103 murder", "purpose": "new"}]}'
    llm = LLMRouter([ScriptedLLM(json_answer=plan)], max_retries=0, backoff=0)
    decomposer = QueryDecomposer(rule_based=RuleBasedDecomposer(container.mapper, 5), llm=llm, use_llm=True,
                                 max_subqueries=5, timeout=2, max_tokens=100)
    q = "Compare IPC 302 and BNS 103"
    result = await decomposer.decompose(q, extract_entities(q))
    assert result.method == "llm" and result.subqueries[0].query == q
    assert len(result.subqueries) <= 5
    no_llm = await decomposer.decompose(q, extract_entities(q), allow_llm=False)
    assert no_llm.method == "rule"


def test_expander_adds_counterpart_provision(container: Container) -> None:
    q = "What does Section 420 IPC say?"
    subqueries = QueryExpander(container.mapper).expand(q, extract_entities(q))
    texts = " | ".join(s.query for s in subqueries)
    assert "Indian Penal Code" in texts and "Bharatiya Nyaya Sanhita, 2023 Section 318(4)" in texts


async def test_reingestion_is_idempotent_and_versions_supersede(container: Container, tmp_path: Path) -> None:
    profile = container.chunk_profiles.get("hierarchical-400")
    report = await container.ingestion.ingest_document(CORPUS / "ipc_fixture.txt", CORPUS, profile)
    assert report.status == "skipped_unchanged"

    doc = tmp_path / "act.txt"
    doc.write_text("Test Act, 2020\n\n1. Short title.—This Act may be called the Test Act.\n", encoding="utf-8")
    (tmp_path / "act.txt.meta.json").write_text('{"document_id": "test-act"}', encoding="utf-8")
    first = await container.ingestion.ingest_document(doc, tmp_path, profile)
    assert first.status == "indexed"
    doc.write_text("Test Act, 2020\n\n1. Short title.—This Act may be called the Test Act, 2020.\n", encoding="utf-8")
    second = await container.ingestion.ingest_document(doc, tmp_path, profile)
    assert second.status == "indexed" and second.version != first.version
    from app.domain.retrieval import RetrievalFilters

    latest = await container.store.scroll(RetrievalFilters(document_ids=["test-act"]), 100)
    everything = await container.store.scroll(RetrievalFilters(document_ids=["test-act"], only_latest=False), 100)
    assert {c.metadata.document_version for c in latest} == {second.version}
    assert {c.metadata.document_version for c in everything} == {first.version, second.version}


async def test_dry_run_writes_nothing(container: Container, tmp_path: Path) -> None:
    doc = tmp_path / "x.txt"
    doc.write_text("Some legal text about contracts and consideration.", encoding="utf-8")
    before = await container.store.count(None)
    report = await container.ingestion.ingest_document(doc, tmp_path, ChunkingProfile(name="r", strategy="recursive"),
                                                       dry_run=True)
    assert report.status == "dry_run" and report.stats and report.stats.chunks == 1
    assert await container.store.count(None) == before


async def test_ingestion_failure_is_reported_not_raised(container: Container, tmp_path: Path) -> None:
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a docx")
    report = await container.ingestion.ingest_document(bad, tmp_path, container.chunk_profiles.get("hierarchical-400"))
    assert report.status == "failed" and report.error


def test_fullwidth_citations_are_normalised_and_uncited_answers_invalid() -> None:
    ctx = _context()
    fullwidth = validate_output("Seven years 【C1】.", ctx, [], [])
    assert fullwidth.valid and fullwidth.cited_ids == ["C1"]
    fake = validate_output("Something 【C9】.", ctx, [], [])
    assert not fake.valid and fake.invalid_citation_ids == ["C9"]
    uncited = validate_output("Seven years.", ctx, [], [])
    assert not uncited.valid and "no evidence passages" in " ".join(uncited.warnings)


def test_mapping_ids_alone_do_not_satisfy_the_citation_requirement() -> None:
    """[M#] notes only say two provisions correspond; factual claims still need [C#] evidence."""
    from app.domain.retrieval import MappingType, ProvisionMapping

    mapping = ProvisionMapping(
        source_act="IPC", source_section="497", target_act="BNS", target_sections=[],
        mapping_type=MappingType.NO_MAPPING, citation_id="M1",
        provenance="test", verification_status="curated_unverified",
    )
    result = validate_output("It was struck down and not carried over [M1].", _context(), [mapping], [])
    assert not result.valid
    assert "no evidence passages" in " ".join(result.warnings)
    # With no evidence passages at all, a mapping-only answer stays valid.
    from app.domain.retrieval import BuiltContext

    empty = validate_output("No corresponding provision exists [M1].", BuiltContext(), [mapping], [])
    assert empty.valid


def test_spaced_citations_are_normalised() -> None:
    from app.services.generation import normalize_citations

    assert normalize_citations("see [ C2 ] and 【 C1 , M1 】") == "see [C2] and [C1, M1]"
    assert validate_output("Seven years [ C1 ].", _context(), [], []).valid


async def test_grounded_subqueries_survive_the_cap_over_llm_guesses(container: Container) -> None:
    """LLM proposals (even plausible-looking ones) never displace entity-grounded look-ups."""
    plan = '{"subqueries": [' + ",".join(
        f'{{"query": "speculative search number {i} about something", "purpose": "guess"}}' for i in range(6)) + "]}"
    llm_provider = ScriptedLLM(json_answer=plan)
    llm = LLMRouter([llm_provider], max_retries=0, backoff=0)
    decomposer = QueryDecomposer(rule_based=RuleBasedDecomposer(container.mapper, 5), llm=llm, use_llm=True,
                                 max_subqueries=5, timeout=2, max_tokens=100)
    q = "What is the BNS equivalent of IPC 302 and what punishment does it prescribe?"
    result = await decomposer.decompose(q, extract_entities(q))
    texts = [s.query for s in result.subqueries]
    assert result.method == "llm" and texts[0] == q
    assert any("Bharatiya Nyaya Sanhita, 2023 Section 103(1)" in t for t in texts)  # mapping counterpart kept
    assert any("Indian Penal Code, 1860 Section 302" in t for t in texts)
    system_prompt = llm_provider.requests[0].messages[0].content
    assert "BNS = Bharatiya Nyaya Sanhita, 2023" in system_prompt  # glossary prevents invented expansions


def test_clause_fragments_keep_their_provision(container: Container) -> None:
    q = "What is the BNS equivalent of IPC 302 and what punishment does it prescribe?"
    parts = [s.query for s in RuleBasedDecomposer(container.mapper, 8).decompose(q, extract_entities(q))]
    fragment = next(p for p in parts if p.lower().startswith("what punishment"))
    assert "302" in fragment


def test_expander_adds_one_lookup_per_compared_provision(container: Container) -> None:
    q = "Explain the difference between Article 14 and Article 21."
    texts = [s.query for s in QueryExpander(container.mapper).expand(q, extract_entities(q))]
    assert texts[0] == q
    assert "Constitution of India Article 14" in texts and "Constitution of India Article 21" in texts
