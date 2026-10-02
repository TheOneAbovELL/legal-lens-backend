"""Service, liveness and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import ContainerDep
from app.schemas.system import HealthResponse, ReadinessResponse, RootResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/",
    response_model=RootResponse,
    summary="Service information",
    description="Minimal service identity. Contains no configuration or sensitive information.",
)
async def root(container: ContainerDep) -> RootResponse:
    return RootResponse(version=container.settings.app_version, docs="/docs" if container.settings.docs else None)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns `healthy` whenever the process is serving requests. It never depends on external "
    "services; use `/ready` for dependency state.",
)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description=(
        "Checks the dependencies required to serve requests: application, embedding model, Qdrant collection, "
        "database and LLM configuration (credentials present; no LLM call is made). The optional knowledge "
        "graph is reported but never blocks readiness. Returns **503** with `failed` listing the unusable "
        "required components."
    ),
    responses={503: {"model": ReadinessResponse, "description": "A required dependency is unavailable"}},
)
async def ready(container: ContainerDep) -> JSONResponse:
    report = await container.readiness()
    return JSONResponse(report.model_dump(mode="json"), status_code=200 if report.status == "ready" else 503)
