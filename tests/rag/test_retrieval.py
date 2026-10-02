from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.container import Container
from app.core.exceptions import RerankingError, RetrievalError
from app.domain.chunks import ChunkMetadata
from app.domain.documents import DocumentType
from app.domain.query import SubQuery
from app.domain.retrieval import RetrievalFilters, RetrievedChunk
from app.rag.fusion import ContextBudget, ContextBuilder, render_context
from app.rag.query.entities import extract_entities
from app.rag.reranking import LexicalReranker, NoopReranker, RerankerSet
from app.rag.retrieval.hybrid import HybridRetriever
from app.rag.retrieval.retrievers import DenseRetriever, MetadataRetriever, SparseRetriever
from app.rag.sparse import SparseEncoder, lexical_terms
from tests.fakes import HashingEmbedder

Q0 = [SubQuery(subquery_id="q0", query="Section 420 IPC cheating punishment", purpose="t", priority=0)]


def test_sparse_encoder_normalises_legal_abbreviations() -> None:
    assert lexical_terms("Sec. 420 of the IPC") == lexical_terms("section 420 IPC")
    enc = SparseEncoder()
    doc = enc.encode_document("cheating cheating property")
    assert len(doc.indices) == 2 and doc.indices == sorted(doc.indices)
    assert enc.encode_query("cheating").values == [1.0]


async def test_dense_sparse_metadata_each_work(container: Container) -> None:
    entities = extract_entities(Q0[0].query)
    for retriever in (DenseRetriever(container.embedder, container.store), SparseRetriever(container.sparse, container.store),
                      MetadataRetriever(container.store)):
        from app.rag.retrieval.base import RetrievalQuery

        hits = await retriever.retrieve(RetrievalQuery(text=Q0[0].query, entities=entities), RetrievalFilters(), 5)
        assert hits, retriever.name
        scores = [h.scores[retriever.name] for h in hits]
        assert scores == sorted(scores, reverse=True), retriever.name
        if retriever.name != "dense":  # the hashing test embedder is not semantically meaningful
            assert any(h.metadata.section == "420" for h in hits), retriever.name
    meta = await MetadataRetriever(container.store).retrieve(
        __import__("app.rag.retrieval.base", fromlist=["RetrievalQuery"]).RetrievalQuery(text="x", entities=entities),
        RetrievalFilters(), 5)
    assert all(h.metadata.section == "420" and h.metadata.act == "IPC" for h in meta)


async def test_hybrid_fusion_dedupes_and_tracks_sources(container: Container) -> None:
    result = await container.retriever.retrieve(
        Q0, extract_entities(Q0[0].query), filters=RetrievalFilters(), candidate_k=10,
        sources=["dense", "sparse", "metadata"],
    )
    ids = [c.chunk_id for c in result.candidates]
    assert len(ids) == len(set(ids))
    top = result.candidates[0]
    assert top.metadata.section == "420"
    assert {"dense", "sparse", "metadata"} <= set(top.sources)
    assert result.timings_ms.keys() >= {"dense", "sparse", "metadata"}


async def test_metadata_filters_restrict_results(container: Container) -> None:
    result = await container.retriever.retrieve(
        Q0, [], filters=RetrievalFilters(acts=["BNS"]), candidate_k=10, sources=["dense", "sparse"]
    )
    assert result.candidates and all(c.metadata.act == "BNS" for c in result.candidates)


async def test_partial_source_failure_degrades_gracefully(container: Container) -> None:
    broken = HashingEmbedder(fail=True)
    retriever = HybridRetriever([DenseRetriever(broken, container.store), SparseRetriever(container.sparse, container.store)])
    result = await retriever.retrieve(Q0, [], filters=None, candidate_k=5, sources=["dense", "sparse"])
    assert result.candidates
    assert [e.source for e in result.errors] == ["dense"]


async def test_all_sources_failing_raises(container: Container) -> None:
    retriever = HybridRetriever([DenseRetriever(HashingEmbedder(fail=True), container.store)])
    with pytest.raises(RetrievalError):
        await retriever.retrieve(Q0, [], filters=None, candidate_k=5, sources=["dense"])


def _chunk(cid: str, text: str, score: float, *, section: str = "1", doc: str = "d", parent: str | None = None,
           level: int = 1, sq: str = "q0") -> RetrievedChunk:
    md = ChunkMetadata(
        chunk_id=cid, document_id=doc, document_version="v", source="s", title="T", document_type=DocumentType.STATUTE,
        jurisdiction="IN", act="IPC", section=section, unit_kind="section", chunking_strategy="x", chunk_profile="p",
        chunk_size=100, overlap=0, token_count=len(text.split()), chunk_index=0, char_start=0, char_end=len(text),
        content_hash=cid, created_at=datetime.now(UTC), parent_chunk_id=parent, hierarchy_level=level,
    )
    return RetrievedChunk(chunk_id=cid, content=text, metadata=md, scores={"dense": score}, fused_score=score,
                          subquery_ids=[sq])


def test_context_fusion_budget_dedup_and_citations() -> None:
    chunks = [
        _chunk("a", "whoever cheats shall be punished with imprisonment for seven years", 0.9, section="420"),
        _chunk("b", "shall be punished with imprisonment for seven years", 0.8, section="420"),  # contained in a
        _chunk("c", "theft is moving movable property dishonestly " * 30, 0.7, section="378"),
        _chunk("d", "irrelevant text", 0.01, section="1"),
    ]
    ctx = ContextBuilder().build(chunks, Q0, ContextBudget(max_context_tokens=100, max_chunks=5,
                                                           min_relative_relevance=0.1))
    ids = [i.chunk.chunk_id for i in ctx.items]
    assert ids[0] == "a"
    assert "b" not in ids  # near-duplicate removed
    assert "c" not in ids  # does not fit the budget: skipped whole, never truncated
    assert "d" not in ids  # below relative relevance floor
    assert ctx.dropped_duplicates >= 1 and ctx.dropped_budget >= 1 and ctx.dropped_low_relevance == 1
    assert [i.citation_id for i in ctx.items] == [f"C{n}" for n in range(1, len(ctx.items) + 1)]
    assert "[C1]" in render_context(ctx)


def test_context_fusion_preserves_subquery_coverage() -> None:
    subqueries = [SubQuery(subquery_id="q0", query="a", purpose="p", priority=0),
                  SubQuery(subquery_id="q1", query="b", purpose="p", priority=1)]
    chunks = [_chunk(f"x{i}", f"alpha text number {i} about topic x", 0.9 - i * 0.01, section=str(i)) for i in range(5)]
    chunks.append(_chunk("y", "beta evidence for the second question", 0.2, section="99", sq="q1"))
    ctx = ContextBuilder().build(chunks, subqueries, ContextBudget(max_chunks=3, min_relative_relevance=0.0))
    assert "y" in [i.chunk.chunk_id for i in ctx.items]  # low score but only evidence for q1


def test_parent_expansion_replaces_children() -> None:
    parent = _chunk("p", "full section text with child one and child two parts", 0.5, level=0)
    child1 = _chunk("c1", "child one", 0.9, parent="p")
    child2 = _chunk("c2", "child two", 0.8, parent="p")
    ctx = ContextBuilder().build([child1, child2, parent], Q0, ContextBudget(min_relative_relevance=0.0))
    assert [i.chunk.chunk_id for i in ctx.items] == ["p"]


async def test_lexical_reranker_prefers_term_coverage_and_exact_provision() -> None:
    a = _chunk("a", "unrelated words about property", 0.9, section="378")
    b = _chunk("b", "cheating punishment seven years", 0.5, section="420")
    ranked = await LexicalReranker().rerank("cheating punishment Section 420 IPC", [a, b],
                                            extract_entities("Section 420 IPC"), 2)
    assert ranked[0].chunk_id == "b" and ranked[0].rerank_score is not None


async def test_reranker_set_falls_back_to_lexical() -> None:
    class Broken(NoopReranker):
        name = "cross_encoder"  # type: ignore[assignment]

        async def rerank(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RerankingError("model missing")

    rerankers = RerankerSet([NoopReranker(), LexicalReranker(), Broken()], fallback="lexical")
    result, used, warning = await rerankers.rerank("cross_encoder", "q", [_chunk("a", "q text", 0.5)], [], 5)
    assert used == "lexical" and warning and result
    strict = RerankerSet([Broken()], fallback=None)
    with pytest.raises(RerankingError):
        await strict.rerank("cross_encoder", "q", [_chunk("a", "q", 0.5)], [], 5)


def test_relevance_floor_is_per_subquery() -> None:
    """A sub-query's evidence must not be dropped because another sub-query scored higher."""
    subqueries = [SubQuery(subquery_id="q0", query="a", purpose="p", priority=0),
                  SubQuery(subquery_id="q1", query="b", purpose="p", priority=1)]
    strong = _chunk("s", "ipc 302 punishment for murder text", 0.95, section="302")
    weak = _chunk("w", "bns 103 punishment for murder in the new code", 0.01, section="103", sq="q1")
    for c, score in ((strong, 0.95), (weak, 0.01)):
        c.rerank_score = score
    ctx = ContextBuilder().build([strong, weak], subqueries, ContextBudget(min_relative_relevance=0.15))
    assert {i.chunk.chunk_id for i in ctx.items} == {"s", "w"}


async def test_hybrid_tracks_best_rank_per_subquery(container: Container) -> None:
    subqueries = [
        SubQuery(subquery_id="q0", query="What is the punishment for murder?", purpose="p", priority=0),
        SubQuery(subquery_id="q1", query="Bharatiya Nyaya Sanhita Section 103 punishment for murder", purpose="p", priority=2),
    ]
    result = await container.retriever.retrieve(subqueries, [], filters=None, candidate_k=30, sources=["sparse"])
    bns103 = next(c for c in result.candidates if c.metadata.act == "BNS" and c.metadata.section == "103")
    assert set(bns103.subquery_ranks) <= {"q0", "q1"} and bns103.subquery_ranks
    assert bns103.primary_subquery({"q0": 0, "q1": 2}) == min(
        bns103.subquery_ranks, key=lambda s: (bns103.subquery_ranks[s], {"q0": 0, "q1": 2}[s]))


def test_exact_provision_hits_are_pinned_despite_low_rerank_scores() -> None:
    """A user-named provision found by exact metadata match is never dropped by reranker scores."""
    named = _chunk("ipc420", "420. Cheating and dishonestly inducing delivery of property", 0.0, section="420")
    named.scores["metadata"] = 1.0
    named.rerank_score = 0.0001  # e.g. an out-of-domain cross-encoder scoring it badly
    others = []
    for i in range(6):
        c = _chunk(f"o{i}", f"unrelated section number {i} about other offences entirely", 0.9, section=str(500 + i))
        c.rerank_score = 0.999
        others.append(c)
    ctx = ContextBuilder().build([*others, named], Q0, ContextBudget(max_chunks=3, min_relative_relevance=0.15))
    ids = [i.chunk.chunk_id for i in ctx.items]
    assert "ipc420" in ids and len(ids) == 3
