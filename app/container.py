"""Application container: builds every long-lived resource once (models, clients, graph) and
exposes them to the API via dependency injection. Tests pass fakes for external services."""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import Settings
from app.core.exceptions import AppError, ConfigurationError
from app.core.logging import get_logger
from app.db.session import Database
from app.graph.builder import build_graph
from app.graph.nodes import PipelineServices
from app.graph.runner import PipelineService
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.embeddings.sentence_transformer import SentenceTransformerEmbedder
from app.providers.graph_db.neo4j_client import Neo4jClient
from app.providers.llm.factory import build_llm_router
from app.providers.llm.router import LLMRouter
from app.providers.vector_store.qdrant_store import QdrantVectorStore
from app.rag.chunking.registry import ChunkingProfileRegistry
from app.rag.fusion import ContextBudget, ContextBuilder
from app.rag.ingestion import IngestionService
from app.rag.profiles import RetrievalProfileSelector
from app.rag.query.complexity import ComplexityConfig, QueryComplexityClassifier
from app.rag.query.decomposition import QueryDecomposer, RuleBasedDecomposer
from app.rag.query.expansion import QueryExpander
from app.rag.query.intent import IntentDetector
from app.rag.reranking import CrossEncoderReranker, LexicalReranker, NoopReranker, Reranker, RerankerSet
from app.rag.retrieval.hybrid import HybridRetriever
from app.rag.retrieval.retrievers import DenseRetriever, GraphRetriever, MetadataRetriever, Retriever, SparseRetriever
from app.rag.sparse import SparseEncoder
from app.schemas.system import ComponentStatus, ReadinessResponse
from app.services.auth import AuthService
from app.services.chat import ChatService
from app.services.conversations import ConversationService
from app.services.generation import AnswerGenerator
from app.services.legal_mapping import LegalProvisionMapper
from app.services.safety import SafetyGuard
from app.services.session_memory import SessionMemory

logger = get_logger(__name__)


class _NotReady(Exception):
    def __init__(self, status: str, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


def build_store(settings: Settings) -> QdrantVectorStore:
    return QdrantVectorStore(
        collection=settings.qdrant_collection,
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
        path=settings.qdrant_path,
        timeout=settings.qdrant_timeout,
        max_retries=settings.qdrant_max_retries,
        dense_vector_name=settings.qdrant_dense_vector_name,
        sparse_vector_name=settings.qdrant_sparse_vector_name,
        allow_create=settings.qdrant_create_collection,
    )


def build_embedder(settings: Settings) -> SentenceTransformerEmbedder:
    return SentenceTransformerEmbedder(
        settings.embedding_model,
        dimension=settings.embedding_dimension,
        device=settings.embedding_device,
        model_version=settings.embedding_version,
        batch_size=settings.embedding_batch_size,
        query_cache_size=settings.embedding_query_cache_size,
    )


def build_neo4j(settings: Settings) -> Neo4jClient | None:
    if not settings.graph_enabled:
        return None
    if not (settings.neo4j_uri and settings.neo4j_user and settings.neo4j_password):
        raise ConfigurationError("NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD are required when Neo4j is enabled")
    return Neo4jClient(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password.get_secret_value(),
        timeout=settings.neo4j_timeout,
        cooldown=settings.neo4j_circuit_cooldown_seconds,
    )


class Container:
    def __init__(
        self,
        settings: Settings,
        *,
        embedder: EmbeddingProvider | None = None,
        store: QdrantVectorStore | None = None,
        llm: LLMRouter | None = None,
        neo4j: Neo4jClient | None | str = "auto",
        cross_encoder: Reranker | None = None,
        database: Database | None = None,
    ) -> None:
        self.settings = settings
        self.embedder = embedder or build_embedder(settings)
        self.store = store or build_store(settings)
        self.llm = llm or build_llm_router(settings)
        self.neo4j = build_neo4j(settings) if neo4j == "auto" else neo4j  # type: ignore[assignment]
        self.database = database or Database(settings.database_url)
        self.sparse = SparseEncoder()
        self.auth = AuthService(settings)
        self.memory = (
            SessionMemory(settings.session_memory_max_turns, settings.session_memory_ttl_seconds,
                          settings.session_memory_max_sessions)
            if settings.session_memory_enabled else None
        )
        self.mapper = LegalProvisionMapper(settings.provision_mapping_path, graph=self.neo4j)
        self.chunk_profiles = ChunkingProfileRegistry.from_file(
            settings.chunking_profiles_path, settings.chunking_default_profile
        )
        self.cross_encoder = cross_encoder or CrossEncoderReranker(settings.reranker_model, settings.reranker_device)

        retrievers: list[Retriever] = [
            DenseRetriever(self.embedder, self.store),
            SparseRetriever(self.sparse, self.store),
            MetadataRetriever(self.store),
        ]
        if self.neo4j is not None:
            retrievers.append(GraphRetriever(self.neo4j))
        self.retriever = HybridRetriever(retrievers)
        self.selector = RetrievalProfileSelector.from_file(
            settings.retrieval_profiles_path,
            default_chunk_profile=settings.chunking_default_profile,
            mode=settings.adaptive_selection_mode,
            evaluation_results=settings.evaluation_results_path,
            available_sources=set(self.retriever.sources),
        )
        rerankers = RerankerSet(
            [NoopReranker(), LexicalReranker(), self.cross_encoder],
            fallback="lexical" if settings.reranker_fallback_to_lexical else None,
        )
        services = PipelineServices(
            intent_detector=IntentDetector(),
            safety_guard=SafetyGuard(),
            complexity_classifier=QueryComplexityClassifier(ComplexityConfig.load(settings.complexity_config_path)),
            profile_selector=self.selector,
            expander=QueryExpander(self.mapper),
            decomposer=QueryDecomposer(
                rule_based=RuleBasedDecomposer(self.mapper, settings.decomposition_max_subqueries),
                llm=self.llm,
                use_llm=settings.decomposition_use_llm,
                max_subqueries=settings.decomposition_max_subqueries,
                timeout=settings.decomposition_timeout,
                max_tokens=settings.decomposition_max_tokens,
            ),
            retriever=self.retriever,
            rerankers=rerankers,
            context_builder=ContextBuilder(),
            mapper=self.mapper,
            generator=AnswerGenerator(self.llm, temperature=settings.llm_temperature, max_tokens=settings.llm_max_tokens),
            memory=self.memory,
            ceiling=ContextBudget(
                max_context_tokens=settings.max_context_tokens,
                max_chunks=settings.max_chunks,
                max_chunks_per_document=settings.max_chunks_per_document,
                max_evidence_per_subquery=settings.max_evidence_per_subquery,
                min_relative_relevance=settings.min_relative_relevance,
            ),
            complexity_routing_enabled=settings.complexity_routing_enabled,
            decomposition_enabled=settings.query_decomposition_enabled,
            max_regenerations=settings.output_validation_max_regenerations,
            evidence_min_term_coverage=settings.evidence_min_term_coverage,
            evidence_min_dense_score=settings.evidence_min_dense_score,
        )
        self.services = services
        self.pipeline = PipelineService(build_graph(services), timeout=settings.pipeline_timeout, memory=self.memory,
                                        diagnostics=settings.diagnostics)
        self.conversations = ConversationService(self.database)
        self.chat = ChatService(self.pipeline, self.conversations)
        self.ingestion = IngestionService(
            embedder=self.embedder, store=self.store, sparse=self.sparse, llm=self.llm,
            embed_batch_size=settings.embedding_batch_size * 4, upsert_batch_size=settings.qdrant_upsert_batch_size,
        )
        self._warmup_task: asyncio.Task[None] | None = None
        self.startup_errors: dict[str, str] = {}

    # ------------------------------------------------------------- lifecycle
    async def startup(self) -> None:
        """Lightweight initialisation: validate config, open clients, check connectivity.

        Never makes LLM calls; the embedding model loads in the background so the server accepts
        requests immediately (``/ready`` reports ``loading`` until it is available).
        """
        st = self.settings
        log = logger.info
        log("Initializing application...")
        if st.db_auto_migrate:
            log("Migrating database...")
            await self.database.migrate()
        log(f"Database ready ({self.database.engine.dialect.name}).")

        log(f"Connecting to Qdrant: {self.store.describe()}...")
        try:
            await self.store.ensure_collection(st.embedding_dimension)
            await self.refresh_index_state()
            log(f"Qdrant ready: {await self.store.count(None)} points; sparse retrieval "
                f"{'enabled' if self.store.sparse_enabled else 'disabled'}; indexed chunk profiles: "
                f"{sorted(self.selector.indexed_chunk_profiles or []) or 'none (run scripts/ingest.py)'}.")
        except AppError as exc:
            # Keep serving /health; /ready reports the dependency failure.
            self.startup_errors["vector_store"] = exc.public_message
            logger.error(f"Qdrant unavailable: {exc.public_message} (check QDRANT_URL / QDRANT_PATH; /ready will report it)",
                         extra={"error_category": exc.code})

        if st.embedding_preload:
            log(f"Loading embedding provider {self.embedder.model_name} ({st.embedding_dimension}-d) in the background...")
            self._warmup_task = asyncio.create_task(self._warmup())
        else:
            log(f"Embedding provider {self.embedder.model_name} will load on first use (EMBEDDING_PRELOAD=false).")

        targets = ", ".join(f"{p.name}:{p.model}" for p in self.llm.providers)
        log(f"Initializing LLM provider chain: {targets} "
            f"({'credentials configured' if self.llm.configured else 'NO credentials: set LLM_API_KEY / GROQ_API_KEY'}).")
        log(f"Knowledge graph: {'enabled' if self.neo4j is not None else 'disabled'}. "
            f"Mapping dataset: {self.mapper.size} entries.")
        nodes = len(getattr(getattr(self.pipeline._graph, "builder", None), "nodes", {}) or {})
        log(f"LangGraph pipeline compiled ({nodes} nodes); complexity routing "
            f"{'on' if st.complexity_routing_enabled else 'off'}; default chunk profile {st.chunking_default_profile}.")
        log("Application ready." + (" Embedding model still loading; /ready returns 503 until it finishes."
                                     if st.embedding_preload and not self.embedder.is_ready else ""))

    async def _warmup(self) -> None:
        try:
            await self.embedder.warmup()
            logger.info(f"Embedding provider loaded: {self.embedder.model_name}. Service is ready.")
        except AppError as exc:
            self.startup_errors["embeddings"] = exc.public_message
            logger.error("embedding model failed to load", extra={"error": str(exc)[:300]})

    async def refresh_index_state(self) -> None:
        sources = set(self.retriever.sources)
        if not self.store.sparse_enabled:
            sources.discard("sparse")
        self.selector.available_sources = sources
        profiles = await self.store.available_profiles()
        self.selector.indexed_chunk_profiles = set(profiles) if profiles else None

    async def readiness(self) -> ReadinessResponse:
        """Dependency state. Lightweight checks only: no LLM calls, no writes."""
        components: list[ComponentStatus] = []

        async def check(name: str, coro: Any, *, required: bool = True, ok_status: str = "ok") -> None:
            try:
                detail = await asyncio.wait_for(coro, timeout=5.0)
                components.append(ComponentStatus(name=name, status=ok_status, required=required, detail=detail or {}))
            except _NotReady as exc:
                components.append(ComponentStatus(name=name, status=exc.status, required=required, error=exc.reason))
            except AppError as exc:
                components.append(ComponentStatus(name=name, status="unavailable", required=required,
                                                  error=exc.public_message))
            except Exception as exc:  # readiness must report, never raise
                components.append(ComponentStatus(name=name, status="unavailable", required=required,
                                                  error=type(exc).__name__))

        async def qdrant() -> dict[str, Any]:
            if "vector_store" in self.startup_errors:
                # Unavailable at startup (e.g. locked or unreachable): finish initialisation once it is back.
                await self.store.ensure_collection(self.settings.embedding_dimension)
                await self.refresh_index_state()
                self.startup_errors.pop("vector_store", None)
                logger.info("Qdrant became available; vector store initialised.")
            info = await self.store.health()
            if not info["exists"]:
                raise _NotReady("failed", "collection missing (run scripts/ingest.py)")
            return {"mode": info["mode"], "collection": info["collection"], "points": await self.store.count(None),
                    "sparse_enabled": self.store.sparse_enabled}

        async def embedding() -> dict[str, Any]:
            if "embeddings" in self.startup_errors:
                raise _NotReady("failed", self.startup_errors["embeddings"])
            if not self.embedder.is_ready:
                raise _NotReady("loading", "embedding model is still loading")
            return {"model": self.embedder.model_name, "dimension": self.embedder.dimension}

        async def llm() -> dict[str, Any]:
            if not self.llm.configured:
                raise _NotReady("not_configured", "no LLM provider credentials configured")
            return {"providers": ", ".join(f"{p.name}:{p.model}" for p in self.llm.providers if p.configured)}

        async def database() -> dict[str, Any]:
            await self.database.ping()
            return {"backend": self.database.engine.dialect.name}

        async def graph_disabled() -> dict[str, Any]:
            raise _NotReady("disabled", "NEO4J_ENABLED is false or NEO4J_URI unset")

        components.append(ComponentStatus(name="application", status="ok", required=True,
                                          detail={"version": self.settings.app_version}))
        await asyncio.gather(
            check("embedding", embedding()),
            check("qdrant", qdrant()),
            check("database", database()),
            check("llm", llm(), ok_status="configured"),
        )
        if self.neo4j is not None:
            await check("knowledge_graph", self.neo4j.verify(), required=False)
        else:
            await check("knowledge_graph", graph_disabled(), required=False)
        failed = [c.name for c in components if c.required and c.status not in ("ok", "configured")]
        return ReadinessResponse(
            status="not_ready" if failed else "ready",
            checks={c.name: c.status for c in components},
            failed=failed,
            components=components,
        )

    async def shutdown(self) -> None:
        if self._warmup_task and not self._warmup_task.done():
            self._warmup_task.cancel()
        for closer in (self.llm.aclose, self.store.close, self.database.close):
            try:
                await closer()
            except Exception as exc:  # best-effort cleanup; log and continue closing the rest
                logger.warning("error during shutdown", extra={"error_type": type(exc).__name__})
        if self.neo4j is not None:
            await self.neo4j.close()
