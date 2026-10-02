from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import PROJECT_ROOT
from app.domain.documents import BlockType, DocumentType, UnitKind
from app.providers.llm.router import LLMRouter
from app.rag.chunking.base import ChunkingProfile
from app.rag.chunking.registry import ChunkingProfileRegistry, build_chunker
from app.rag.chunking.segments import split_sentences
from app.rag.documents.cleaner import clean_text
from app.rag.ingestion import prepare
from tests.conftest import CORPUS
from tests.fakes import HashingEmbedder, ScriptedLLM

REGISTRY = ChunkingProfileRegistry.from_file(PROJECT_ROOT / "config" / "chunking_profiles.json")


def ipc():  # type: ignore[no-untyped-def]
    return prepare(CORPUS / "ipc_fixture.txt", CORPUS)


def test_structure_extraction_finds_sections_and_blocks() -> None:
    doc = ipc()
    assert doc.document.document_type == DocumentType.STATUTE and doc.document.act == "IPC"
    sections = {u.number: u for u in doc.units if u.kind == UnitKind.SECTION}
    assert set(sections) == {"299", "300", "302", "378", "379", "415", "420"}
    assert sections["420"].heading == "Cheating and dishonestly inducing delivery of property"
    assert [b.block_type for b in sections["299"].blocks].count(BlockType.EXPLANATION) == 2
    assert [b.block_type for b in sections["300"].blocks].count(BlockType.EXCEPTION) == 2
    assert BlockType.ILLUSTRATION in [b.block_type for b in sections["378"].blocks]
    assert sections["420"].chapter and "XVII" in sections["420"].chapter


def test_constitution_articles_and_clauses() -> None:
    doc = prepare(CORPUS / "constitution_fixture.txt", CORPUS)
    articles = {u.number: u for u in doc.units if u.kind == UnitKind.ARTICLE}
    assert set(articles) == {"14", "19", "21"}
    assert BlockType.CLAUSE in [b.block_type for b in articles["19"].blocks]


def test_cleaner_rejoins_hyphenation_and_drops_page_numbers() -> None:
    assert clean_text("commit-\nted the offence\n  12  \nnext") == "committed the offence\nnext\n"


def test_sentence_splitter_respects_legal_abbreviations() -> None:
    text = "See s. 420 of the I.P.C. for cheating. The accused was convicted. Maneka Gandhi v. Union of India held so."
    sentences = [text[s.start:s.end] for s in split_sentences(text, 0, len(text))]
    assert sentences[0] == "See s. 420 of the I.P.C. for cheating."
    assert len(sentences) == 3


def test_document_version_is_content_hash_and_deterministic() -> None:
    a, b = ipc(), ipc()
    assert a.document.version == b.document.version
    assert a.document.version == f"v-{a.document.content_hash[:12]}"


@pytest.mark.parametrize("name", ["fixed-300-50", "sentence-250", "recursive-500-50", "sliding-3-2", "hierarchical-250"])
async def test_every_strategy_shares_metadata_model_and_respects_sections(name: str) -> None:
    doc = ipc()
    chunks = await build_chunker(REGISTRY.get(name)).chunk(doc)
    assert chunks
    text = doc.document.text
    for c in chunks:
        md = c.metadata
        assert md.chunking_strategy == REGISTRY.get(name).strategy and md.chunk_profile == name
        assert text[md.char_start:md.char_end] == c.content  # offsets are exact
        assert md.content_hash and md.document_version == doc.document.version
        unit = next(u for u in doc.units if u.start <= md.char_start < max(u.end, u.start + 1))
        assert md.char_end <= unit.end  # never crosses a section boundary
        if md.section:
            assert md.section == unit.number
            assert "Indian Penal Code" in c.context_header


async def test_chunk_ids_deterministic_and_unique() -> None:
    doc = ipc()
    first = await build_chunker(REGISTRY.get("recursive-500-50")).chunk(doc)
    second = await build_chunker(REGISTRY.get("recursive-500-50")).chunk(doc)
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
    assert len({c.chunk_id for c in first}) == len(first)


async def test_small_chunk_size_splits_but_keeps_overlap_and_limits() -> None:
    doc = ipc()
    profile = ChunkingProfile(name="fixed-40-10", strategy="fixed", chunk_size=40, overlap=10)
    chunks = await build_chunker(profile).chunk(doc)
    s299 = [c for c in chunks if c.metadata.section == "299"]
    assert len(s299) > 2
    assert all(c.metadata.token_count <= 40 for c in chunks)
    assert s299[1].metadata.char_start < s299[0].metadata.char_end  # overlapping windows


async def test_hierarchical_parent_child_links() -> None:
    doc = ipc()
    profile = ChunkingProfile(name="h-40", strategy="hierarchical", chunk_size=40, overlap=0, params={"parent_max_tokens": 400})
    chunks = await build_chunker(profile).chunk(doc)
    parents = {c.chunk_id: c for c in chunks if c.metadata.hierarchy_level == 0}
    children = [c for c in chunks if c.metadata.parent_chunk_id]
    assert parents and children
    for child in children:
        parent = parents[child.metadata.parent_chunk_id]  # type: ignore[index]
        assert parent.metadata.char_start <= child.metadata.char_start and child.metadata.char_end <= parent.metadata.char_end


async def test_semantic_chunker_records_boundary_info() -> None:
    doc = ipc()
    profile = ChunkingProfile(name="sem", strategy="semantic", chunk_size=60, params={"threshold_type": "percentile", "threshold": 50})
    chunks = await build_chunker(profile, embedder=HashingEmbedder()).chunk(doc)
    assert any(c.metadata.semantic_boundary and c.metadata.semantic_boundary["method"] == "embedding_distance" for c in chunks)


async def test_ai_chunker_falls_back_on_invalid_llm_output() -> None:
    doc = ipc()
    llm = LLMRouter([ScriptedLLM(["not json"], json_answer="not json")], max_retries=0, backoff=0)
    profile = ChunkingProfile(name="ai", strategy="ai", chunk_size=40)
    chunks = await build_chunker(profile, llm=llm).chunk(doc)
    assert chunks and all(c.metadata.chunking_strategy == "ai" for c in chunks)


async def test_ai_chunker_uses_valid_llm_boundaries() -> None:
    doc = ipc()
    llm = LLMRouter([ScriptedLLM(json_answer='{"boundaries": [1]}')], max_retries=0, backoff=0)
    profile = ChunkingProfile(name="ai", strategy="ai", chunk_size=60)
    chunks = await build_chunker(profile, llm=llm).chunk(doc)
    assert any(c.metadata.semantic_boundary and c.metadata.semantic_boundary.get("method") == "llm" for c in chunks)


def test_profile_validation() -> None:
    with pytest.raises(ValueError):
        ChunkingProfile(name="bad", strategy="fixed", chunk_size=100, overlap=100)


def test_pdf_loader_paginates(tmp_path: Path) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    path = tmp_path / "blank.pdf"
    with path.open("wb") as fh:
        writer.write(fh)
    from app.core.exceptions import DocumentProcessingError
    from app.rag.documents.loaders import load_document

    with pytest.raises(DocumentProcessingError, match="no extractable text"):
        load_document(path)
