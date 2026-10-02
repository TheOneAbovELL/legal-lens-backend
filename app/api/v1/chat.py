"""Chat endpoints — all served by the single canonical LangGraph pipeline."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Request
from fastapi.responses import StreamingResponse

from app.api.deps import ContainerDep, OptionalUser, RateLimited
from app.api.errors import responses
from app.api.v1.common import SSE_HEADERS, build_options, check_query, public_result, request_id, sse
from app.core.config import Settings
from app.graph.runner import PipelineResult
from app.graph.state import PipelineMode
from app.schemas.chat import CHAT_EXAMPLES, ChatRequest, ChatResponse
from app.schemas.common import BnsAlert

router = APIRouter(tags=["Chat"])

ChatBody = Annotated[ChatRequest, Body(openapi_examples=CHAT_EXAMPLES)]
_ERRORS = responses(401, 413, 422, 429, 502, 503, 504)

SSE_DOC = (
    "Server-Sent Events: one JSON object per `data:` line, in order: `start`, `intent`, `safety`, `complexity`, "
    "`plan`, `retrieval`, `reranking`, `evidence`, `bns_alert`, `token`… (real provider deltas), `citation`…, "
    "`validation`, then `done` (full result) or `error`. Test it with `python scripts/test_stream.py`; Swagger "
    "buffers SSE and shows the raw events only after the stream ends."
)
_SSE_RESPONSE = {200: {"description": SSE_DOC, "content": {"text/event-stream": {"example":
                       'data: {"type": "start", "request_id": "..."}\n\ndata: {"type": "token", "content": "Section"}\n\n'
                       'data: {"type": "done", "answer": "...", "citations": [...]}\n\n'}}}}


def to_chat_response(result: PipelineResult, settings: Settings) -> ChatResponse:
    result = public_result(result, settings)
    return ChatResponse(
        answer=result.answer,
        source="qdrant" if result.evidence else "none",
        request_id=result.metadata.request_id,
        refused=result.refused,
        citations=result.citations,
        bns_alerts=[BnsAlert.from_mapping(m) for m in result.mappings],
        warnings=result.warnings,
        disclaimer=result.disclaimer,
        metadata=result.metadata,
        diagnostics=result.diagnostics,
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[RateLimited],
    summary="Ask a legal question",
    description=(
        "Runs the full pipeline: intent → safety → complexity routing (SIMPLE/MODERATE/COMPLEX) → planning "
        "(expansion / decomposition) → hybrid retrieval (dense + sparse + metadata [+ graph]) → reranking → "
        "context fusion → IPC↔BNS mapping → evidence gate → grounded generation → citation validation.\n\n"
        "Returns JSON by default. With `stream: true` or `Accept: text/event-stream` it returns SSE "
        "(see `/api/v1/chat/stream`). Requires a bearer token only when `AUTH_REQUIRED=true`."
    ),
    responses={**_ERRORS, 200: {"description": "JSON answer (or SSE when streaming is requested)"}},
)
async def chat(body: ChatBody, request: Request, container: ContainerDep, user: OptionalUser):  # type: ignore[no-untyped-def]
    query = check_query(container, body.query)
    options = build_options(mode=PipelineMode.ANSWER, user=user, role=body.user_role, profile=body.profile,
                            filters=body.filters, session_id=body.session_id)
    wants_stream = body.stream or "text/event-stream" in request.headers.get("accept", "")
    if wants_stream:
        events = container.pipeline.stream(request_id(), query, options)
        return StreamingResponse(sse(events), media_type="text/event-stream", headers=SSE_HEADERS)
    return to_chat_response(await container.pipeline.run(request_id(), query, options), container.settings)


# The original API served POST /api/v1/chat/ (trailing slash); keep it working without a redirect.
router.add_api_route("/chat/", chat, methods=["POST"], response_model=ChatResponse, include_in_schema=False,
                     dependencies=[RateLimited])


@router.post(
    "/chat/stream",
    dependencies=[RateLimited],
    summary="Ask a legal question (Server-Sent Events)",
    description=SSE_DOC,
    response_class=StreamingResponse,
    responses={**_ERRORS, **_SSE_RESPONSE},
)
async def chat_stream(body: ChatBody, container: ContainerDep, user: OptionalUser) -> StreamingResponse:
    query = check_query(container, body.query)
    options = build_options(mode=PipelineMode.ANSWER, user=user, role=body.user_role, profile=body.profile,
                            filters=body.filters, session_id=body.session_id)
    events = container.pipeline.stream(request_id(), query, options)
    return StreamingResponse(sse(events), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post(
    "/query/stream",
    dependencies=[RateLimited],
    deprecated=True,
    summary="Legacy plain-text token stream",
    description="Kept for clients of the previous API. Streams only answer text (real LLM tokens). "
    "Use `/api/v1/chat/stream` instead.",
    response_class=StreamingResponse,
    responses={**_ERRORS, 200: {"description": "text/plain token stream",
                                "content": {"text/plain": {"example": "Section 420 IPC punishes cheating…"}}}},
)
async def legacy_query_stream(body: ChatBody, container: ContainerDep, user: OptionalUser) -> StreamingResponse:
    query = check_query(container, body.query)
    options = build_options(mode=PipelineMode.ANSWER, user=user, role=body.user_role, session_id=body.session_id)

    async def text_tokens():  # type: ignore[no-untyped-def]
        async for event in container.pipeline.stream(request_id(), query, options):
            if event["type"] == "token":
                yield event["content"]
            elif event["type"] == "error":
                yield f"\n[error: {event['message']}]"

    return StreamingResponse(text_tokens(), media_type="text/plain; charset=utf-8",
                             headers={**SSE_HEADERS, "Deprecation": "true"})
