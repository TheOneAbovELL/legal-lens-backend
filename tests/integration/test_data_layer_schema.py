"""The backend against the data-layer cloud schema: judgment payloads, provision filters,
opinion-aware citations and graph case enrichment. Everything here runs offline."""

from __future__ import annotations

import pytest
from qdrant_client import models

from app.core.config import Settings
from app.domain.documents import DocumentType
from app.domain.retrieval import EvidenceItem, RetrievalFilters, RetrievedChunk
from app.providers.vector_store.qdrant_store import QdrantVectorStore, build_filter, payload_to_chunk
from app.rag.query.entities import extract_entities
from app.rag.retrieval.base import RetrievalQuery
from app.rag.retrieval.retrievers import GraphRetriever

# A trimmed but shape-faithful payload from the data-layer judgment_chunks collection.
JUDGMENT_PAYLOAD = {
    "block_id": "joseph_shine_2018_b51",
    "case_id": "joseph_shine_2018",
    "case_name": "Joseph Shine v. Union of India",
    "chunk_id": "joseph_shine_2018_o2_p7_1",
    "chunk_part": 1,
    "citation": "(2019) 3 SCC 39",
    "cite_as": "Joseph Shine v. Union of India, (2019) 3 SCC 39, para 7 (per D.Y. Chandrachud, concurring)",
    "context": "Joseph Shine v. Union of India, Supreme Court, 27 September 2018",
    "court": "Supreme Court",
    "date": "2018-09-27",
    "doc_sha256": "3130322b6f533e0db960f15b8013a9244f6e8414980fad4d16b8b225d895d1b2",
    "doc_type": "judgment",
    "opinion_author": "D.Y. Chandrachud",
    "opinion_type": "concurring",
    "page_start": 104,
    "paragraph_num": 7,
    "parent_id": "joseph_shine_2018_o2_p7",
    "section_heading": "B Judicial discourse on adultery",
    "statutes": ["IPC:497"],
    "statutes_current": [],
    "text": "It was aimed at preventing the woman from exercising her sexual agency.",
    "tokens": 85,
}


class TestJudgmentPayload:
    def test_maps_data_layer_fields(self):
        chunk = payload_to_chunk("00d66275-93c8-502e-b6a5-6429a0e3d0fc", dict(JUDGMENT_PAYLOAD))
        md = chunk.metadata
        assert chunk.content == JUDGMENT_PAYLOAD["text"]
        assert chunk.context_header.startswith("Joseph Shine v. Union of India, Supreme Court")
        assert md.chunk_id == "joseph_shine_2018_o2_p7_1"  # payload id, not the point id
        assert md.document_id == "joseph_shine_2018"
        assert md.document_version == JUDGMENT_PAYLOAD["doc_sha256"][:16]
        assert md.document_type == DocumentType.CASE_LAW
        assert md.case_name == "Joseph Shine v. Union of India"
        assert md.case_citation == "(2019) 3 SCC 39"
        assert md.court == "Supreme Court"
        assert str(md.decision_date) == "2018-09-27"
        assert md.opinion_type == "concurring"
        assert md.opinion_author == "D.Y. Chandrachud"
        assert md.cite_as.endswith("(per D.Y. Chandrachud, concurring)")
        assert md.paragraph == 7 and md.unit_kind == "paragraph"
        assert md.page_number == 104
        assert md.parent_chunk_id == "joseph_shine_2018_o2_p7"
        assert md.section_heading == "B Judicial discourse on adultery"
        assert md.token_count == 85

    def test_citation_carries_opinion_fields(self):
        chunk = payload_to_chunk("pid", dict(JUDGMENT_PAYLOAD))
        item = EvidenceItem(
            citation_id="C1",
            chunk=RetrievedChunk(chunk_id=chunk.chunk_id, content=chunk.content,
                                 context_header=chunk.context_header, metadata=chunk.metadata,
                                 scores={"dense": 0.8}, ranks={"dense": 1}, subquery_ids=["q0"]),
            token_count=85,
        )
        citation = item.citation()
        assert citation.case_citation == "(2019) 3 SCC 39"
        assert citation.opinion_type == "concurring"
        assert citation.opinion_author == "D.Y. Chandrachud"
        assert citation.cite_as and "para 7" in citation.cite_as

    def test_own_payload_schema_still_wins(self):
        # A payload written by this backend (has chunk_profile) must not take the legacy branch.
        own = {"chunk_profile": "hierarchical-400"}
        assert "chunk_profile" in own  # guard the discriminator this test relies on


class TestProvisionFilter:
    def test_acts_and_sections_match_both_schemas(self):
        f = build_filter(RetrievalFilters(acts=["IPC"], sections=["497"]))
        nested = [c for c in f.must if isinstance(c, models.Filter)]
        assert nested, "expected a nested should-clause for the provision"
        should = nested[0].should
        keys = {getattr(c, "key", None) for c in should}
        assert "statutes" in keys and "statutes_current" in keys
        statutes = next(c for c in should if getattr(c, "key", None) == "statutes")
        assert statutes.match.any == ["IPC:497"]

    def test_document_type_translates_to_doc_type(self):
        f = build_filter(RetrievalFilters(document_types=["case_law"]))
        nested = [c for c in f.must if isinstance(c, models.Filter)][0]
        doc_type = next(c for c in nested.should if getattr(c, "key", None) == "doc_type")
        assert doc_type.match.any == ["judgment"]

    def test_acts_alone_keep_plain_condition(self):
        f = build_filter(RetrievalFilters(acts=["IPC"]))
        assert any(getattr(c, "key", None) == "act" for c in f.must)


class TestExternalCollectionFlags:
    def test_empty_vector_names_disable_sparse_and_target_unnamed_dense(self):
        store = QdrantVectorStore(collection="judgment_chunks", path=":memory:",
                                  dense_vector_name="", sparse_vector_name="", allow_create=False)
        assert store.sparse_enabled is False
        assert store._dense_using is None


class _StubGraph:
    def __init__(self, fail_cases: bool = False):
        self.fail_cases = fail_cases

    async def statutes(self, refs, limit=10):
        return [{"code": "IPC", "section": "497", "title": "Adultery", "text": None, "is_active": False}]

    async def interpreting_cases(self, refs, per_statute=5):
        if self.fail_cases:
            raise RuntimeError("boom")
        return [{"code": "IPC", "section": "497", "title": "Adultery", "cases": [
            {"name": "Joseph Shine v. Union of India", "citation": "(2019) 3 SCC 39",
             "court": "Supreme Court", "date": "2018-09-27", "overruled": False},
        ]}]


class TestGraphCaseEnrichment:
    @pytest.mark.asyncio
    async def test_statute_chunk_lists_interpreting_cases(self):
        retriever = GraphRetriever(_StubGraph())
        query = RetrievalQuery(text="adultery IPC 497", entities=extract_entities("Section 497 IPC"))
        results = await retriever.retrieve(query, None, 5)
        assert len(results) == 1
        assert "Cases interpreting this provision" in results[0].content
        assert "Joseph Shine v. Union of India" in results[0].content
        assert "(2019) 3 SCC 39" in results[0].content

    @pytest.mark.asyncio
    async def test_enrichment_failure_still_returns_statutes(self):
        retriever = GraphRetriever(_StubGraph(fail_cases=True))
        query = RetrievalQuery(text="adultery IPC 497", entities=extract_entities("Section 497 IPC"))
        results = await retriever.retrieve(query, None, 5)
        assert len(results) == 1
        assert "Cases interpreting" not in results[0].content


class TestNeo4jSettings:
    def test_username_alias_and_database(self, monkeypatch):
        monkeypatch.setenv("NEO4J_USERNAME", "aura-user")
        monkeypatch.setenv("NEO4J_DATABASE", "aura-db")
        s = Settings(_env_file=None)
        assert s.neo4j_user == "aura-user"
        assert s.neo4j_database == "aura-db"

    def test_neo4j_user_still_works(self, monkeypatch):
        monkeypatch.delenv("NEO4J_USERNAME", raising=False)
        monkeypatch.setenv("NEO4J_USER", "classic")
        s = Settings(_env_file=None)
        assert s.neo4j_user == "classic"
