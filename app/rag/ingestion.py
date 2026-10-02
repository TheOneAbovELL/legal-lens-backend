"""Document ingestion: load → clean → structure → chunk (per profile) → enrich → embed → index → validate.

Deterministic re-ingestion: chunk IDs derive from (document, version, profile, index, content
hash), a document version derives from its content hash, and an already fully indexed
(document, version, profile) is skipped. A new version is indexed alongside the old one, then the
old version is flagged ``is_latest=false`` (kept for audit, excluded from retrieval).
"""

from __future__ import annotations

import statistics
import time
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.exceptions import AppError, DocumentProcessingError
from app.core.logging import get_logger
from app.core.text import sha256
from app.domain.acts import canonical_act
from app.domain.chunks import Chunk
from app.domain.documents import DocumentType, SourceDocument, StructuredDocument
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.llm.router import LLMRouter
from app.providers.vector_store.qdrant_store import QdrantVectorStore
from app.rag.chunking.base import ChunkingProfile
from app.rag.chunking.registry import build_chunker
from app.rag.documents.cleaner import clean_text
from app.rag.documents.loaders import RawDocument, load_document, slugify
from app.rag.documents.structure import extract_structure, infer_act, infer_document_type
from app.rag.sparse import SparseEncoder

logger = get_logger(__name__)


class ChunkStats(BaseModel):
    chunks: int
    min_tokens: int = 0
    max_tokens: int = 0
    mean_tokens: float = 0.0
    total_tokens: int = 0


class DocumentReport(BaseModel):
    path: str
    document_id: str
    version: str
    document_type: str
    units: int
    profile: str
    status: str  # indexed | skipped_unchanged | dry_run | failed | up_to_date | stale | missing
    stats: ChunkStats | None = None
    written: int = 0
    error: str | None = None
    seconds: float = 0.0


class IngestionReport(BaseModel):
    documents: list[DocumentReport] = Field(default_factory=list)

    @property
    def failed(self) -> list[DocumentReport]:
        return [d for d in self.documents if d.status == "failed"]


def _parse_date(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise DocumentProcessingError(f"invalid date {value!r} in metadata sidecar") from exc


def build_source_document(raw: RawDocument, source_root: Path) -> SourceDocument:
    pages = [clean_text(p) for p in raw.pages]
    offsets, parts, cursor = [], [], 0
    for page in pages:
        offsets.append(cursor)
        parts.append(page)
        cursor += len(page) + 1
    text = "\n".join(parts)
    if not text.strip():
        raise DocumentProcessingError(f"{raw.path.name}: document is empty after cleaning")

    meta = raw.metadata
    try:
        relative = raw.path.resolve().relative_to(source_root.resolve())
    except ValueError:
        relative = Path(raw.path.name)
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), raw.path.stem)
    title = str(meta.get("title") or first_line[:200])
    doc_type = DocumentType(meta["document_type"]) if meta.get("document_type") else infer_document_type(text, title)
    content_hash = sha256(text)
    return SourceDocument(
        document_id=str(meta.get("document_id") or slugify(str(relative.with_suffix("")))),
        version=str(meta.get("version") or f"v-{content_hash[:12]}"),
        title=title,
        source=str(meta.get("source") or relative.as_posix()),
        document_type=doc_type,
        jurisdiction=str(meta.get("jurisdiction") or "IN"),
        act=canonical_act(meta.get("act")) or meta.get("act") or infer_act(text, title),
        effective_date=_parse_date(meta.get("effective_date")),
        publication_date=_parse_date(meta.get("publication_date")),
        content_hash=content_hash,
        text=text,
        case_name=meta.get("case_name"),
        case_citation=meta.get("case_citation"),
        court=meta.get("court"),
        decision_date=_parse_date(meta.get("decision_date")),
        page_offsets=offsets if raw.paginated else [],
    )


def prepare(path: Path, source_root: Path) -> StructuredDocument:
    return extract_structure(build_source_document(load_document(path), source_root))


def chunk_stats(chunks: list[Chunk]) -> ChunkStats:
    tokens = [c.metadata.token_count for c in chunks]
    if not tokens:
        return ChunkStats(chunks=0)
    return ChunkStats(chunks=len(tokens), min_tokens=min(tokens), max_tokens=max(tokens),
                      mean_tokens=round(statistics.fmean(tokens), 1), total_tokens=sum(tokens))


class IngestionService:
    def __init__(
        self,
        *,
        embedder: EmbeddingProvider,
        store: QdrantVectorStore,
        sparse: SparseEncoder,
        llm: LLMRouter | None = None,
        embed_batch_size: int = 64,
        upsert_batch_size: int = 64,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._sparse = sparse
        self._llm = llm
        self._embed_batch = embed_batch_size
        self._upsert_batch = upsert_batch_size

    async def chunk(self, document: StructuredDocument, profile: ChunkingProfile) -> list[Chunk]:
        chunker = build_chunker(profile, embedder=self._embedder, llm=self._llm)
        chunks = await chunker.chunk(document)
        for chunk in chunks:
            chunk.metadata.embedding_model = self._embedder.model_name
            chunk.metadata.embedding_version = self._embedder.model_version
        return chunks

    async def index_chunks(self, chunks: list[Chunk]) -> int:
        written = 0
        for start in range(0, len(chunks), self._embed_batch):
            batch = chunks[start : start + self._embed_batch]
            texts = [c.embedding_text for c in batch]
            dense = await self._embedder.embed_documents(texts)
            sparse = [self._sparse.encode_document(t) for t in texts]
            written += await self._store.upsert(batch, dense, sparse, batch_size=self._upsert_batch)
        return written

    async def ingest_document(
        self, path: Path, source_root: Path, profile: ChunkingProfile, *, dry_run: bool = False, force: bool = False
    ) -> DocumentReport:
        started = time.perf_counter()
        try:
            document = prepare(path, source_root)
        except DocumentProcessingError as exc:
            return DocumentReport(path=str(path), document_id="?", version="?", document_type="?", units=0,
                                  profile=profile.name, status="failed", error=str(exc))
        doc = document.document
        report = DocumentReport(path=str(path), document_id=doc.document_id, version=doc.version,
                                document_type=doc.document_type.value, units=len(document.units), profile=profile.name,
                                status="dry_run")
        try:
            chunks = await self.chunk(document, profile)
            report.stats = chunk_stats(chunks)
            if dry_run:
                return report
            existing = await self._store.count_version(doc.document_id, doc.version, profile.name)
            if existing == len(chunks) and not force:
                report.status = "skipped_unchanged"
                return report
            report.written = await self.index_chunks(chunks)
            await self._store.mark_superseded(doc.document_id, doc.version)
            indexed = await self._store.count_version(doc.document_id, doc.version, profile.name)
            if indexed < len(chunks):
                raise DocumentProcessingError(f"validation failed: {indexed}/{len(chunks)} chunks present in index")
            report.status = "indexed"
        except AppError as exc:  # report per-document failure, keep ingesting the others
            logger.error("ingestion failed", extra={"path": str(path), "error_category": exc.code})
            report.status, report.error = "failed", str(exc)
        finally:
            report.seconds = round(time.perf_counter() - started, 3)
        return report

    async def validate_document(self, path: Path, source_root: Path, profile: ChunkingProfile) -> DocumentReport:
        """Compare a source file with the index without writing anything."""
        document = prepare(path, source_root)
        doc = document.document
        chunks = await self.chunk(document, profile) if profile.strategy not in ("semantic", "ai") else None
        indexed = await self._store.count_version(doc.document_id, doc.version, profile.name)
        versions = await self._store.document_versions(doc.document_id)
        if indexed and (chunks is None or indexed == len(chunks)):
            status = "up_to_date"
        elif versions:
            status = "stale"
        else:
            status = "missing"
        return DocumentReport(path=str(path), document_id=doc.document_id, version=doc.version,
                              document_type=doc.document_type.value, units=len(document.units), profile=profile.name,
                              status=status, stats=chunk_stats(chunks) if chunks else None, written=indexed)
