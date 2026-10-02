"""FastAPI application factory.

Importing this module builds the app object only; models, clients and the graph are created in
the lifespan (``Container``), never at import time.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.errors import install_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.rate_limit import SlidingWindowRateLimiter
from app.api.v1 import auth, chat, conversations, diagnostics, health, search, statutes
from app.container import Container
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger("app.startup")

DESCRIPTION = """
Grounded legal-information retrieval and question answering for Indian law.

**Start here**
1. `GET /ready` — every required dependency should be `ok` / `configured`.
2. `POST /api/v1/diagnostics/route` — see how a question is classified and routed (no LLM).
3. `POST /api/v1/search` — inspect retrieval results and stage diagnostics (no LLM).
4. `POST /api/v1/chat` — full answer with citations.
5. Optional auth: `POST /api/v1/auth/signup` → copy `access_token` → **Authorize**.

Legal Lens provides legal *information*, not legal advice. It never predicts outcomes or gives strategy.
"""

TAGS = [
    {"name": "Health", "description": "Service identity, liveness and readiness probes."},
    {"name": "Authentication",
     "description": "Signup/login with bcrypt + signed JWT. Use **Authorize** for protected endpoints."},
    {"name": "Chat", "description": "Grounded legal Q&A through the single LangGraph pipeline (JSON or SSE)."},
    {"name": "Conversations", "description": "Persisted chat history, scoped to the authenticated user."},
    {"name": "Search", "description": "Hybrid retrieval only (no LLM unless requested) with stage diagnostics."},
    {"name": "Statutes", "description": "IPC↔BNS, CrPC↔BNSS, IEA↔BSA provision mapping with provenance."},
    {"name": "Diagnostics", "description": "Development checks for Qdrant, embeddings, LLM, routing and config. "
                                           "Disabled in production unless DIAGNOSTICS_ENABLED=true."},
]


def _banner(settings: Settings) -> None:
    base = settings.public_base_url.rstrip("/")
    line = "=" * 58
    lines = [line, "LEGAL LENS BACKEND", line, f"Environment: {settings.app_env.value}",
             f"Version:     {settings.app_version}", f"API:         {base}"]
    if settings.docs:
        lines += [f"Docs:        {base}/docs", f"ReDoc:       {base}/redoc", f"OpenAPI:     {base}/openapi.json"]
    lines += [f"Health:      {base}/health", f"Ready:       {base}/ready"]
    if settings.diagnostics:
        lines.append(f"Diagnostics: {base}/api/v1/diagnostics/config")
    lines.append(line)
    for text in lines:
        logger.info(text)


def create_app(
    settings: Settings | None = None, container_factory: Callable[[Settings], Container] | None = None
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.json_logs)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _banner(settings)
        container = (container_factory or Container)(settings)
        app.state.container = container
        app.state.rate_limiter = SlidingWindowRateLimiter(
            settings.rate_limit_requests, settings.rate_limit_window_seconds, settings.rate_limit_max_clients
        )
        await container.startup()
        try:
            yield
        finally:
            logger.info("Shutting down: closing LLM, vector store, database and graph clients...")
            await container.shutdown()
            logger.info("Shutdown complete.")

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        summary="Legal Lens backend API",
        description=DESCRIPTION,
        openapi_tags=TAGS,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs else None,
        redoc_url="/redoc" if settings.docs else None,
        openapi_url="/openapi.json" if settings.docs else None,
        swagger_ui_parameters={"persistAuthorization": True, "displayRequestDuration": True, "tryItOutEnabled": True},
    )
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(RequestContextMiddleware, max_body_bytes=settings.max_request_bytes)

    app.include_router(health.router)
    for router in (auth.router, chat.router, conversations.router, search.router, statutes.router,
                   diagnostics.router):
        app.include_router(router, prefix="/api/v1")
    _mount_frontend(app, settings)
    return app


def _mount_frontend(app: FastAPI, settings: Settings) -> None:
    """Optionally serve the built single-page frontend from this process (FRONTEND_DIST_PATH).

    API, docs and health routes keep precedence; every other GET falls back to index.html so client-side
    routes survive a refresh. Separate hosting (nginx, CDN) remains the recommended production setup.
    """
    dist = settings.frontend_dist_path
    if dist is None:
        return
    index = dist / "index.html"
    if not index.is_file():
        logger.warning(f"FRONTEND_DIST_PATH set but {index} is missing; serving the API only.")
        return
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str, request: Request):  # type: ignore[no-untyped-def]
        if path.startswith(("api/", "docs", "redoc", "openapi.json", "health", "ready")):
            raise StarletteHTTPException(status_code=404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    logger.info(f"Serving frontend from {dist}")


app = create_app()
