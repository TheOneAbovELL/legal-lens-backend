"""Helpers shared by v1 routers: pipeline options and SSE encoding."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from app.container import Container
from app.core.config import Settings
from app.core.exceptions import InvalidQueryError
from app.core.logging import request_id_var
from app.db.models import User
from app.graph.runner import PipelineResult, trim_for_public
from app.graph.state import PipelineMode, PipelineOptions
from app.schemas.common import SearchFilters
from app.services.generation import UserRole

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


def request_id() -> str:
    return request_id_var.get() or "unknown"


def check_query(container: Container, query: str) -> str:
    query = query.strip()
    if not query:
        raise InvalidQueryError("empty query", public_message="The query must not be empty.")
    if len(query) > container.settings.max_query_chars:
        raise InvalidQueryError(
            "query too long", public_message=f"The query must be at most {container.settings.max_query_chars} characters."
        )
    return query


def build_options(
    *,
    mode: PipelineMode,
    user: User | None,
    role: str | None = None,
    profile: str | None = None,
    filters: SearchFilters | None = None,
    top_k: int | None = None,
    session_id: str | None = None,
    allow_llm: bool = True,
) -> PipelineOptions:
    resolved_role = role or (user.role if user else None) or UserRole.CITIZEN.value
    return PipelineOptions(
        mode=mode,
        allow_llm=allow_llm,
        profile_override=profile,
        top_k=top_k,
        filters=filters.to_domain() if filters else None,
        user_role=UserRole(resolved_role),
        # Memory is namespaced by user so sessions can never leak across accounts.
        session_key=f"{user.id if user else 'anon'}:{session_id}" if session_id else None,
    )


async def sse(events: AsyncIterator[dict[str, Any]]) -> AsyncIterator[str]:
    async for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def public_result(result: PipelineResult, settings: Settings) -> PipelineResult:
    """Production trims diagnostic detail; secrets are never present in either mode."""
    return result if settings.diagnostics else trim_for_public(result)
