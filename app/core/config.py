"""Centralised, validated application settings.

All runtime configuration is environment-driven (optionally via a ``.env`` file).
Nothing else in the codebase reads ``os.environ`` directly.
"""

from __future__ import annotations

import secrets
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AppEnv(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,  # allow Settings(app_env=...) as well as the APP_ENV/ENV aliases
    )

    # ---- application ----
    app_name: str = "Legal Lens"
    app_env: AppEnv = Field(default=AppEnv.DEVELOPMENT, validation_alias=AliasChoices("APP_ENV", "ENV"))
    app_version: str = "2.0.0"
    log_level: str = "INFO"
    log_json: bool | None = None  # None -> JSON in production, readable text otherwise
    # Public URL printed in the startup banner (uvicorn's bind address is not visible to the app).
    public_base_url: str = "http://127.0.0.1:8000"
    #: Optional: serve a built frontend (frontend/dist) from this process; empty/missing -> API only.
    frontend_dist_path: Path | None = None
    # Safe structured diagnostics (retrieval stages, sub-queries, timings) in responses and the
    # /api/v1/diagnostics endpoints. None -> enabled everywhere except production.
    diagnostics_enabled: bool | None = None
    docs_enabled: bool | None = None  # Swagger/ReDoc; None -> enabled except in production

    # ---- HTTP / security ----
    cors_origins: CsvList = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173",
                                 "http://localhost:3000", "http://127.0.0.1:3000"]
    )
    max_request_bytes: int = Field(default=64 * 1024, ge=1024)
    max_query_chars: int = Field(default=4000, ge=10)
    rate_limit_enabled: bool = True
    rate_limit_requests: int = Field(default=30, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    rate_limit_max_clients: int = Field(default=10_000, ge=100)

    # ---- authentication ----
    auth_required: bool = False
    auth_allow_registration: bool = True
    jwt_secret_key: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "legal-lens"
    access_token_expire_minutes: int = Field(default=60, ge=1, le=60 * 24 * 7)

    # ---- database (users) ----
    database_url: str = f"sqlite+aiosqlite:///{(PROJECT_ROOT / 'data' / 'legal_lens.db').as_posix()}"
    db_auto_migrate: bool = True

    # ---- vector store ----
    qdrant_url: str | None = None
    qdrant_api_key: SecretStr | None = None
    qdrant_path: str | None = None  # embedded on-disk mode; ":memory:" for ephemeral
    qdrant_collection: str = "legal-lens-chunks"
    # Named vectors. An empty dense name targets the unnamed default vector of an externally
    # created collection; an empty sparse name disables sparse retrieval for that collection.
    qdrant_dense_vector_name: str = "dense"
    qdrant_sparse_vector_name: str = "sparse"
    qdrant_create_collection: bool = True
    qdrant_timeout: float = Field(default=10.0, gt=0)
    qdrant_max_retries: int = Field(default=2, ge=0, le=10)
    qdrant_upsert_batch_size: int = Field(default=64, ge=1, le=1024)

    # ---- embeddings ----
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"
    embedding_dimension: int = Field(default=1024, ge=8)
    embedding_version: str = "1"
    embedding_batch_size: int = Field(default=16, ge=1)
    embedding_query_cache_size: int = Field(default=512, ge=0)
    embedding_preload: bool = True

    # ---- reranker ----
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_device: str = "cpu"
    reranker_fallback_to_lexical: bool = True

    # ---- LLM ----
    llm_provider: str = "groq"
    # llama-3.1-8b-instant (the previous default) now returns HTTP 404 on Groq.
    llm_model: str = "openai/gpt-oss-120b"
    llm_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("LLM_API_KEY", "GROQ_API_KEY")
    )
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=1024, ge=16, le=32_768)
    llm_timeout: float = Field(default=30.0, gt=0)
    llm_retry_enabled: bool = True
    llm_max_retries: int = Field(default=2, ge=0, le=10)
    llm_backoff: float = Field(default=0.5, ge=0.0, description="Base backoff seconds")
    llm_backoff_max: float = Field(default=8.0, ge=0.0)
    # Ordered "provider:model" targets. Empty -> [llm_provider:llm_model].
    llm_provider_order: CsvList = Field(default_factory=list)
    # Reasoning models (matched by model-name prefix) get these extra parameters. Hidden reasoning
    # is never streamed to users; without a low effort it can consume the whole token budget.
    llm_reasoning_model_prefixes: CsvList = Field(default_factory=lambda: ["openai/gpt-oss", "qwen/qwen3"])
    llm_reasoning_effort: str | None = Field(default="low", pattern="^(low|medium|high)$")

    # ---- knowledge graph (optional) ----
    neo4j_enabled: bool | None = None  # None -> enabled iff NEO4J_URI is set
    neo4j_uri: str | None = None
    neo4j_user: str | None = Field(default=None, validation_alias=AliasChoices("NEO4J_USER", "NEO4J_USERNAME"))
    neo4j_password: SecretStr | None = None
    neo4j_database: str | None = None  # None -> the server's default database
    neo4j_timeout: float = Field(default=5.0, gt=0)
    neo4j_circuit_cooldown_seconds: float = Field(default=60.0, ge=0)

    # ---- retrieval / context ----
    # Per-path budgets live in the retrieval profiles; these are global hard ceilings.
    default_top_k: int = Field(default=8, ge=1, le=100)
    max_context_tokens: int = Field(default=6000, ge=100)
    max_chunks: int = Field(default=16, ge=1)
    max_chunks_per_document: int = Field(default=8, ge=1)
    max_evidence_per_subquery: int = Field(default=4, ge=1)
    min_relative_relevance: float = Field(default=0.15, ge=0.0, le=1.0)
    # Evidence gate (absolute relevance). Evidence is sufficient when an exact provision/graph hit
    # exists, OR the evidence covers this fraction of the query's content terms, OR the best dense
    # cosine reaches the threshold. The dense threshold is model-specific: calibrate it with
    # scripts/evaluate_chunking.py on labelled data before relying on it.
    evidence_min_term_coverage: float = Field(default=0.34, ge=0.0, le=1.0)
    evidence_min_dense_score: float = Field(default=0.6, ge=0.0, le=1.0)
    retrieval_profiles_path: Path = PROJECT_ROOT / "config" / "retrieval_profiles.json"

    # ---- routing / decomposition ----
    complexity_routing_enabled: bool = True
    complexity_config_path: Path | None = None
    query_decomposition_enabled: bool = True
    decomposition_use_llm: bool = True
    decomposition_max_subqueries: int = Field(default=5, ge=1, le=10)
    decomposition_timeout: float = Field(default=10.0, gt=0)
    decomposition_max_tokens: int = Field(default=600, ge=64)
    pipeline_timeout: float = Field(default=90.0, gt=0)

    # ---- answer verification ----
    # One bounded regeneration when the answer cites unknown evidence IDs or provisions that
    # are absent from the evidence (non-streaming responses only).
    output_validation_max_regenerations: int = Field(default=1, ge=0, le=2)

    # ---- MEM-0: short-term, non-persistent session memory ----
    session_memory_enabled: bool = True
    session_memory_max_turns: int = Field(default=4, ge=1, le=20)
    session_memory_ttl_seconds: int = Field(default=1800, ge=60)
    session_memory_max_sessions: int = Field(default=5000, ge=10)

    # ---- chunking / ingestion ----
    chunking_default_profile: str = "hierarchical-400"
    chunking_profiles_path: Path = PROJECT_ROOT / "config" / "chunking_profiles.json"
    adaptive_selection_mode: str = Field(default="rules", pattern="^(rules|data_driven)$")
    evaluation_results_path: Path = PROJECT_ROOT / "evaluation" / "results" / "latest.json"
    data_dir: Path = PROJECT_ROOT / "data"
    provision_mapping_path: Path = PROJECT_ROOT / "data" / "mappings" / "ipc_bns.json"

    _split_lists = field_validator(
        "cors_origins", "llm_provider_order", "llm_reasoning_model_prefixes", mode="before"
    )(_split_csv)

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        value = value.upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"invalid LOG_LEVEL {value!r}")
        return value

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        if self.app_env == AppEnv.PRODUCTION:
            secret = self.jwt_secret_key.get_secret_value() if self.jwt_secret_key else ""
            if len(secret) < 32:
                raise ValueError("JWT_SECRET_KEY of at least 32 characters is required in production")
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS origins are not allowed in production")
        if not self.qdrant_url and not self.qdrant_path:
            # Embedded local store keeps development usable without a server.
            self.qdrant_path = (self.data_dir / "qdrant").as_posix()
        return self

    # ---- derived helpers ----
    @property
    def is_production(self) -> bool:
        return self.app_env == AppEnv.PRODUCTION

    @property
    def json_logs(self) -> bool:
        return self.is_production if self.log_json is None else self.log_json

    @property
    def diagnostics(self) -> bool:
        return (not self.is_production) if self.diagnostics_enabled is None else self.diagnostics_enabled

    @property
    def docs(self) -> bool:
        return (not self.is_production) if self.docs_enabled is None else self.docs_enabled

    @property
    def graph_enabled(self) -> bool:
        if self.neo4j_enabled is None:
            return bool(self.neo4j_uri)
        return self.neo4j_enabled

    @property
    def llm_targets(self) -> list[tuple[str, str]]:
        """Ordered (provider, model) pairs used by the retry/fallback router."""
        raw = self.llm_provider_order or [f"{self.llm_provider}:{self.llm_model}"]
        targets: list[tuple[str, str]] = []
        for item in raw:
            provider, sep, model = item.partition(":")
            if not sep or not model:
                raise ValueError(f"LLM_PROVIDER_ORDER entry {item!r} must be 'provider:model'")
            targets.append((provider.strip().lower(), model.strip()))
        return targets

    def jwt_secret(self) -> str:
        if self.jwt_secret_key:
            return self.jwt_secret_key.get_secret_value()
        return _ephemeral_secret()


@lru_cache(maxsize=1)
def _ephemeral_secret() -> str:
    # Development only: tokens become invalid on restart. Production requires JWT_SECRET_KEY.
    return secrets.token_urlsafe(48)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
