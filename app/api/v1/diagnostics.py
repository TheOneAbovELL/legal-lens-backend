"""Development diagnostics (enabled unless APP_ENV=production or DIAGNOSTICS_ENABLED=false).

Read-only component checks for Qdrant, embeddings, the LLM provider and query routing. When
AUTH_REQUIRED=true these endpoints require a bearer token like every other protected endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import ContainerDep, OptionalUser
from app.api.errors import ERROR_RESPONSES
from app.core.exceptions import AppError
from app.schemas.system import (
    ConfigSummary,
    EmbeddingDiagnostics,
    LLMCheckRequest,
    LLMDiagnostics,
    QdrantDiagnostics,
    RouteDiagnostics,
    RouteRequest,
)
from app.services import diagnostics


class DiagnosticsDisabled(AppError):
    code = "not_found"
    http_status = 404
    public_message = "Diagnostics are disabled in this environment."


async def require_diagnostics(container: ContainerDep, user: OptionalUser) -> None:
    if not container.settings.diagnostics:
        raise DiagnosticsDisabled()


router = APIRouter(prefix="/diagnostics", tags=["Diagnostics"], dependencies=[Depends(require_diagnostics)],
                   responses={404: ERROR_RESPONSES[404], 401: ERROR_RESPONSES[401]})


@router.get("/config", response_model=ConfigSummary, summary="Effective configuration (no secrets)",
            description="Which providers, models, profiles and features are active. Credentials are reported only "
            "as configured/not configured.")
async def config(container: ContainerDep) -> ConfigSummary:
    return diagnostics.config_summary(container)


@router.get("/qdrant", response_model=QdrantDiagnostics, summary="Verify Qdrant",
            description="Connection, collection existence, vector name/dimension/distance, sparse vector config, "
            "point count, indexed chunk profiles and a read-only probe query. Never writes.")
async def qdrant(container: ContainerDep) -> QdrantDiagnostics:
    return await diagnostics.check_qdrant(container)


@router.get("/embedding", response_model=EmbeddingDiagnostics, summary="Verify the embedding model",
            description="Embeds a probe sentence and checks dimension, finiteness, non-zero output and L2 "
            "normalization. Loads the model if it is not loaded yet (can take ~30 s the first time).")
async def embedding(container: ContainerDep) -> EmbeddingDiagnostics:
    return await diagnostics.check_embedding(container)


@router.post("/llm", response_model=LLMDiagnostics, summary="Verify the LLM provider (makes one small call)",
             description="Sends a minimal prompt through the configured retry/fallback chain with a short timeout "
             "and a small token limit. Not run automatically at startup.")
async def llm(container: ContainerDep, body: LLMCheckRequest | None = None) -> LLMDiagnostics:
    body = body or LLMCheckRequest()
    return await diagnostics.check_llm(container, body.prompt, body.max_tokens)


@router.post("/route", response_model=RouteDiagnostics, summary="Inspect intent, safety, complexity and routing",
             description="Runs the deterministic front of the pipeline — normalization, entities, intent, safety, "
             "complexity, profile selection and query planning — without retrieval or generation. Use it to "
             "check SIMPLE / MODERATE / COMPLEX routing and the structured sub-queries for complex questions.")
async def route(body: RouteRequest, container: ContainerDep) -> RouteDiagnostics:
    return await diagnostics.check_route(container, body.query, body.use_llm_decomposition)
