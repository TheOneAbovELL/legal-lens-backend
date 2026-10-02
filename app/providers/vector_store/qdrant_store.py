"""Qdrant vector store: the only module that knows Qdrant's API.

Supports Qdrant Cloud/server (``QDRANT_URL``), embedded on-disk mode (``QDRANT_PATH``) and
ephemeral in-memory mode (``QDRANT_PATH=:memory:``, used by tests and evaluation).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, TypeVar
from urllib.parse import urlparse

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.core.exceptions import ConfigurationError, VectorStoreError
from app.core.logging import get_logger
from app.core.retry import retry_async
from app.core.text import sha256
from app.domain.chunks import Chunk, ChunkMetadata
from app.domain.documents import DocumentType
from app.domain.retrieval import RetrievalFilters
from app.rag.sparse import SparseVector

logger = get_logger(__name__)
T = TypeVar("T")

_KEYWORD_INDEXES = (
    "document_id", "document_version", "chunk_profile", "chunking_strategy", "act", "section",
    "document_type", "jurisdiction", "content_hash", "court",
)
_PAYLOAD_EXCLUDE = {"embedding_model", "embedding_version"}  # stored, but set at index time


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, ResponseHandlingException):  # connection / timeout
        return True
    if isinstance(exc, UnexpectedResponse):
        return exc.status_code in {429, 500, 502, 503, 504}
    return isinstance(exc, (TimeoutError, ConnectionError))


def chunk_to_payload(chunk: Chunk) -> dict[str, Any]:
    payload = chunk.metadata.model_dump(mode="json")
    payload["content"] = chunk.content
    payload["context_header"] = chunk.context_header
    return payload


def payload_to_chunk(point_id: str, payload: dict[str, Any]) -> Chunk:
    """Parse our payload, or map an externally loaded (legacy) payload onto ChunkMetadata."""
    content = payload.get("content") or payload.get("text") or ""
    if "chunk_profile" in payload:
        meta = ChunkMetadata.model_validate({k: v for k, v in payload.items() if k in ChunkMetadata.model_fields})
        return Chunk(content=content, context_header=payload.get("context_header", ""), metadata=meta)
    # Legacy schema (e.g. judgment_chunks: case_id, case_name, paragraph_num, court, date, text).
    document_id = str(payload.get("case_id") or payload.get("statute_id") or payload.get("source") or "external")
    title = str(payload.get("case_name") or payload.get("title") or document_id)
    paragraph = payload.get("paragraph_num")
    decision_date = payload.get("date")
    meta = ChunkMetadata(
        chunk_id=str(point_id),
        document_id=document_id,
        document_version=str(payload.get("version", "external")),
        source=str(payload.get("source", "qdrant")),
        title=title,
        document_type=DocumentType.CASE_LAW if payload.get("case_id") else DocumentType.OTHER,
        jurisdiction=str(payload.get("jurisdiction", "IN")),
        act=payload.get("code"),
        section=str(payload["section"]) if payload.get("section") is not None else None,
        paragraph=int(paragraph) if isinstance(paragraph, (int, float, str)) and str(paragraph).isdigit() else None,
        case_name=payload.get("case_name"),
        case_citation=payload.get("citation"),
        court=payload.get("court"),
        decision_date=str(decision_date)[:10] if decision_date else None,
        chunking_strategy="external",
        chunk_profile="external",
        chunk_size=0,
        overlap=0,
        token_count=len(content.split()),
        chunk_index=int(paragraph) if isinstance(paragraph, int) else 0,
        char_start=0,
        char_end=len(content),
        content_hash=sha256(content),
        created_at=datetime(1970, 1, 1, tzinfo=UTC),
    )
    return Chunk(content=content, metadata=meta)


def build_filter(filters: RetrievalFilters | None) -> models.Filter | None:
    if filters is None:
        return None
    must: list[models.Condition] = []
    must_not: list[models.Condition] = []

    def any_of(key: str, values: list[str] | None) -> None:
        if values:
            must.append(models.FieldCondition(key=key, match=models.MatchAny(any=list(values))))

    any_of("document_id", filters.document_ids)
    any_of("document_type", filters.document_types)
    any_of("act", filters.acts)
    any_of("section", filters.sections)
    any_of("chunk_profile", filters.chunk_profiles)
    any_of("court", filters.courts)
    if filters.decided_after or filters.decided_before:
        must.append(
            models.FieldCondition(
                key="decision_date",
                range=models.DatetimeRange(
                    gte=filters.decided_after.isoformat() if filters.decided_after else None,
                    lte=filters.decided_before.isoformat() if filters.decided_before else None,
                ),
            )
        )
    if filters.jurisdiction:
        must.append(models.FieldCondition(key="jurisdiction", match=models.MatchValue(value=filters.jurisdiction)))
    if filters.only_latest:
        # must_not(false) keeps legacy points that carry no is_latest flag.
        must_not.append(models.FieldCondition(key="is_latest", match=models.MatchValue(value=False)))
    if not must and not must_not:
        return None
    return models.Filter(must=must or None, must_not=must_not or None)


class QdrantVectorStore:
    def __init__(
        self,
        *,
        collection: str,
        url: str | None = None,
        api_key: str | None = None,
        path: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 2,
        dense_vector_name: str = "dense",
        sparse_vector_name: str = "sparse",
        allow_create: bool = True,
    ) -> None:
        self._init_error: str | None = None
        self._path: str | None = None
        if url:
            self._client = AsyncQdrantClient(url=url, api_key=api_key, timeout=int(timeout))
            self.mode = "remote"
        elif path == ":memory:":
            self._client = AsyncQdrantClient(location=":memory:")
            self.mode = "memory"
        elif path:
            self.mode = "local"
            self._path = path
            self._client = None  # type: ignore[assignment]
            self._open_local()
        else:
            raise ConfigurationError("either QDRANT_URL or QDRANT_PATH must be configured")
        self.target = urlparse(url).hostname or url if url else (path or "")
        self.collection = collection
        self.dense_name = dense_vector_name
        self.sparse_name = sparse_vector_name
        self._allow_create = allow_create
        self._max_retries = max_retries
        self.sparse_enabled = bool(sparse_vector_name)

    def _open_local(self) -> None:
        """Open the embedded store; if another process holds its lock, record why (retried on next call)."""
        try:
            self._client = AsyncQdrantClient(path=self._path)
            self._init_error = None
        except RuntimeError as exc:
            if "already accessed" not in str(exc):
                raise
            # Embedded Qdrant allows one process. Keep the app up; calls report this clearly until free.
            self._init_error = (
                f"embedded Qdrant store {self._path} is in use by another process (e.g. a running uvicorn or "
                "ingest). Stop that process, or run a Qdrant server and set QDRANT_URL."
            )

    def describe(self) -> str:
        """Human-readable target for logs/CLI (host or local path only; never credentials)."""
        return f"{self.mode} Qdrant at {self.target} (collection {self.collection!r})"

    # ---------------------------------------------------------------- helpers
    async def _call(self, name: str, op: Callable[[], Awaitable[T]]) -> T:
        if self._init_error and self.mode == "local":
            self._open_local()  # the other process may have released the lock
        if self._init_error:
            raise VectorStoreError(self._init_error, public_message="The embedded vector store is locked by another process.")
        try:
            return await retry_async(
                op, retries=self._max_retries, is_retryable=_is_transient, operation_name=f"qdrant.{name}"
            )
        except (ResponseHandlingException, UnexpectedResponse, TimeoutError, ConnectionError) as exc:
            raise VectorStoreError(f"qdrant {name} failed: {type(exc).__name__}: {exc}") from exc

    @property
    def _dense_using(self) -> str | None:
        return self.dense_name or None

    # ------------------------------------------------------------- collection
    async def ensure_collection(self, dimension: int) -> None:
        exists = await self._call("collection_exists", lambda: self._client.collection_exists(self.collection))
        if not exists:
            if not self._allow_create:
                raise ConfigurationError(f"Qdrant collection {self.collection!r} does not exist")
            await self._create_collection(dimension)
            return
        await self.validate_collection(dimension)

    async def _create_collection(self, dimension: int) -> None:
        dense = models.VectorParams(size=dimension, distance=models.Distance.COSINE)
        vectors_config: Any = {self.dense_name: dense} if self.dense_name else dense
        sparse_config = (
            {self.sparse_name: models.SparseVectorParams(modifier=models.Modifier.IDF)}
            if self.sparse_name
            else None
        )
        await self._call(
            "create_collection",
            lambda: self._client.create_collection(
                self.collection, vectors_config=vectors_config, sparse_vectors_config=sparse_config
            ),
        )
        if self.mode == "remote":  # payload indexes are a no-op in embedded mode
            for field in _KEYWORD_INDEXES:
                await self._call(
                    "create_payload_index",
                    lambda f=field: self._client.create_payload_index(
                        self.collection, f, models.PayloadSchemaType.KEYWORD
                    ),
                )
            await self._call(
                "create_payload_index",
                lambda: self._client.create_payload_index(self.collection, "is_latest", models.PayloadSchemaType.BOOL),
            )
        logger.info("qdrant collection created", extra={"collection": self.collection, "dimension": dimension})

    async def validate_collection(self, dimension: int) -> dict[str, Any]:
        info = await self._call("get_collection", lambda: self._client.get_collection(self.collection))
        vectors = info.config.params.vectors
        if isinstance(vectors, dict):
            params = vectors.get(self.dense_name) if self.dense_name else None
        else:
            params = vectors if not self.dense_name else None
        if params is None:
            raise ConfigurationError(
                f"collection {self.collection!r} has no dense vector named {self.dense_name!r}; "
                "set QDRANT_DENSE_VECTOR_NAME to match it (empty string for an unnamed vector)"
            )
        if params.size != dimension:
            raise ConfigurationError(
                f"collection {self.collection!r} vector size {params.size} != EMBEDDING_DIMENSION {dimension}"
            )
        if params.distance != models.Distance.COSINE:
            raise ConfigurationError(f"collection {self.collection!r} must use cosine distance")
        sparse = info.config.params.sparse_vectors or {}
        if self.sparse_name and self.sparse_name not in sparse:
            logger.warning(
                "sparse vector not present in collection; sparse retrieval disabled",
                extra={"collection": self.collection, "sparse_vector": self.sparse_name},
            )
            self.sparse_enabled = False
        return {"points": info.points_count, "status": str(info.status)}

    # ----------------------------------------------------------------- writes
    async def upsert(
        self,
        chunks: list[Chunk],
        dense: list[list[float]],
        sparse: list[SparseVector] | None,
        *,
        batch_size: int = 64,
    ) -> int:
        if len(chunks) != len(dense) or (sparse is not None and len(sparse) != len(chunks)):
            raise VectorStoreError("upsert called with mismatched chunk/vector counts")
        written = 0
        for start in range(0, len(chunks), batch_size):
            points = []
            for i in range(start, min(start + batch_size, len(chunks))):
                vector: Any
                if self.dense_name:
                    vector = {self.dense_name: dense[i]}
                    if sparse is not None and self.sparse_enabled and sparse[i].indices:
                        vector[self.sparse_name] = models.SparseVector(
                            indices=sparse[i].indices, values=sparse[i].values
                        )
                else:
                    vector = dense[i]
                points.append(models.PointStruct(id=chunks[i].chunk_id, vector=vector, payload=chunk_to_payload(chunks[i])))
            await self._call("upsert", lambda p=points: self._client.upsert(self.collection, points=p, wait=True))
            written += len(points)
        return written

    async def mark_superseded(self, document_id: str, current_version: str) -> None:
        """Flag older versions of a document as not-latest (kept for audit, excluded from search)."""
        selector = models.Filter(
            must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))],
            must_not=[models.FieldCondition(key="document_version", match=models.MatchValue(value=current_version))],
        )
        await self._call(
            "set_payload",
            lambda: self._client.set_payload(self.collection, payload={"is_latest": False}, points=selector, wait=True),
        )

    # ------------------------------------------------------------------ reads
    async def search_dense(
        self, vector: list[float], filters: RetrievalFilters | None, limit: int
    ) -> list[tuple[Chunk, float]]:
        response = await self._call(
            "query_dense",
            lambda: self._client.query_points(
                self.collection, query=vector, using=self._dense_using, query_filter=build_filter(filters),
                limit=limit, with_payload=True,
            ),
        )
        return [(payload_to_chunk(str(p.id), p.payload or {}), float(p.score)) for p in response.points]

    async def search_sparse(
        self, vector: SparseVector, filters: RetrievalFilters | None, limit: int
    ) -> list[tuple[Chunk, float]]:
        if not self.sparse_enabled or not vector.indices:
            return []
        response = await self._call(
            "query_sparse",
            lambda: self._client.query_points(
                self.collection,
                query=models.SparseVector(indices=vector.indices, values=vector.values),
                using=self.sparse_name, query_filter=build_filter(filters), limit=limit, with_payload=True,
            ),
        )
        return [(payload_to_chunk(str(p.id), p.payload or {}), float(p.score)) for p in response.points]

    async def scroll(self, filters: RetrievalFilters | None, limit: int) -> list[Chunk]:
        points, _ = await self._call(
            "scroll",
            lambda: self._client.scroll(
                self.collection, scroll_filter=build_filter(filters), limit=limit, with_payload=True, with_vectors=False
            ),
        )
        return [payload_to_chunk(str(p.id), p.payload or {}) for p in points]

    async def count(self, filters: RetrievalFilters | None = None) -> int:
        result = await self._call(
            "count", lambda: self._client.count(self.collection, count_filter=build_filter(filters), exact=True)
        )
        return int(result.count)

    async def count_version(self, document_id: str, version: str, profile: str) -> int:
        selector = models.Filter(must=[
            models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id)),
            models.FieldCondition(key="document_version", match=models.MatchValue(value=version)),
            models.FieldCondition(key="chunk_profile", match=models.MatchValue(value=profile)),
        ])
        result = await self._call(
            "count", lambda: self._client.count(self.collection, count_filter=selector, exact=True)
        )
        return int(result.count)

    async def document_versions(self, document_id: str) -> set[str]:
        chunks = await self.scroll(
            RetrievalFilters(document_ids=[document_id], only_latest=False), limit=10_000
        )
        return {c.metadata.document_version for c in chunks}

    async def available_profiles(self) -> list[str] | None:
        """Distinct chunk profiles present in the index (None if it cannot be determined)."""
        try:
            response = await self._client.facet(self.collection, key="chunk_profile", limit=100, exact=True)
            return sorted(str(hit.value) for hit in response.hits)
        except Exception as exc:  # facet unsupported (old server / embedded mode): fall back to scroll
            logger.debug("facet unavailable, falling back to scroll", extra={"error_type": type(exc).__name__})
        try:
            chunks = await self.scroll(None, limit=10_000)
        except VectorStoreError:
            return None
        return sorted({c.metadata.chunk_profile for c in chunks})

    async def describe_collection(self) -> dict[str, Any]:
        """Read-only collection facts for diagnostics."""
        exists = await self._call("collection_exists", lambda: self._client.collection_exists(self.collection))
        if not exists:
            return {"exists": False}
        info = await self._call("get_collection", lambda: self._client.get_collection(self.collection))
        vectors = info.config.params.vectors
        params = vectors.get(self.dense_name) if isinstance(vectors, dict) else vectors
        sparse = info.config.params.sparse_vectors or {}
        return {
            "exists": True,
            "points": info.points_count,
            "dense_vector": self.dense_name or "(unnamed)",
            "dimension": params.size if params else None,
            "distance": str(params.distance.value) if params else None,
            "sparse_vectors": sorted(sparse),
        }

    async def health(self) -> dict[str, Any]:
        exists = await self._call("collection_exists", lambda: self._client.collection_exists(self.collection))
        return {"mode": self.mode, "collection": self.collection, "exists": exists}

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
