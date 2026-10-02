"""Concrete retrievers: dense (vector), sparse (BM25-style lexical), metadata (exact provision
filters) and knowledge-graph (Neo4j statutes)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.text import count_tokens, sha256
from app.domain.acts import act_display_name
from app.domain.chunks import CHUNK_NAMESPACE, ChunkMetadata
from app.domain.documents import DocumentType
from app.domain.retrieval import RetrievalFilters, RetrievedChunk
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.graph_db.neo4j_client import Neo4jClient
from app.providers.vector_store.qdrant_store import QdrantVectorStore
from app.rag.query.entities import provision_refs
from app.rag.retrieval.base import RetrievalQuery, Retriever, to_retrieved
from app.rag.sparse import SparseEncoder


class DenseRetriever(Retriever):
    name = "dense"

    def __init__(self, embedder: EmbeddingProvider, store: QdrantVectorStore) -> None:
        self._embedder = embedder
        self._store = store

    async def retrieve(self, query: RetrievalQuery, filters: RetrievalFilters | None, top_k: int) -> list[RetrievedChunk]:
        vector = await self._embedder.embed_query(query.text)
        hits = await self._store.search_dense(vector, filters, top_k)
        return [to_retrieved(c, self.name, s, i + 1, query.subquery_id) for i, (c, s) in enumerate(hits)]


class SparseRetriever(Retriever):
    name = "sparse"

    def __init__(self, encoder: SparseEncoder, store: QdrantVectorStore) -> None:
        self._encoder = encoder
        self._store = store

    async def retrieve(self, query: RetrievalQuery, filters: RetrievalFilters | None, top_k: int) -> list[RetrievedChunk]:
        hits = await self._store.search_sparse(self._encoder.encode_query(query.text), filters, top_k)
        return [to_retrieved(c, self.name, s, i + 1, query.subquery_id) for i, (c, s) in enumerate(hits)]


class MetadataRetriever(Retriever):
    """Exact payload match on (act, section/article) for provisions named in the query.

    Vector similarity is weak at "Section 420 IPC" vs "Section 421 IPC"; an exact metadata filter
    is cheap and precise. Results are returned in document order with a constant score.
    """

    name = "metadata"
    per_subquery = False

    def __init__(self, store: QdrantVectorStore, max_refs: int = 6) -> None:
        self._store = store
        self._max_refs = max_refs

    async def retrieve(self, query: RetrievalQuery, filters: RetrievalFilters | None, top_k: int) -> list[RetrievedChunk]:
        base = filters or RetrievalFilters()
        results: list[RetrievedChunk] = []
        for act, number in provision_refs(query.entities)[: self._max_refs]:
            chunks = await self._store.scroll(base.merged(acts=[act], sections=[number]), limit=top_k)
            chunks.sort(key=lambda c: (c.metadata.document_id, c.metadata.hierarchy_level, c.metadata.char_start))
            results.extend(
                to_retrieved(c, self.name, 1.0, len(results) + i + 1, query.subquery_id) for i, c in enumerate(chunks)
            )
        return results[:top_k] if len(results) > top_k else results


class GraphRetriever(Retriever):
    """Statute nodes from the Neo4j knowledge graph for provisions named in the query."""

    name = "graph"
    per_subquery = False

    def __init__(self, client: Neo4jClient) -> None:
        self._client = client

    async def retrieve(self, query: RetrievalQuery, filters: RetrievalFilters | None, top_k: int) -> list[RetrievedChunk]:
        refs = provision_refs(query.entities)
        if not refs:
            return []
        rows = await self._client.statutes(refs, limit=top_k)
        results = []
        for rank, row in enumerate(rows, start=1):
            code, section = str(row.get("code") or "").upper(), str(row.get("section") or "")
            title = row.get("title") or ""
            content = row.get("text") or f"{act_display_name(code)} Section {section}: {title}".strip()
            chunk_id = str(uuid.uuid5(CHUNK_NAMESPACE, f"neo4j|{code}|{section}"))
            meta = ChunkMetadata(
                chunk_id=chunk_id,
                document_id=f"neo4j:{code}",
                document_version="graph",
                source="neo4j",
                title=act_display_name(code) or code,
                document_type=DocumentType.STATUTE,
                jurisdiction="IN",
                act=code,
                section=section,
                unit_kind="section",
                section_heading=title or None,
                chunking_strategy="knowledge_graph",
                chunk_profile="knowledge_graph",
                chunk_size=0,
                overlap=0,
                token_count=count_tokens(content),
                chunk_index=0,
                char_start=0,
                char_end=len(content),
                content_hash=sha256(content),
                created_at=datetime(1970, 1, 1, tzinfo=UTC),
                is_latest=row.get("is_active") is not False,
            )
            results.append(RetrievedChunk(
                chunk_id=chunk_id, content=content, context_header=f"{act_display_name(code)} › Section {section}",
                metadata=meta, scores={self.name: 1.0}, ranks={self.name: rank}, subquery_ids=[query.subquery_id],
            ))
        return results
