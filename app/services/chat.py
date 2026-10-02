"""AskLegalQuestion use case: runs the canonical pipeline and persists the exchange.

Persistence rules (identical for JSON and SSE):
* anonymous caller            -> stateless; nothing is written, ``persisted`` is False;
* authenticated, no id        -> a conversation is created (titled from the question);
* authenticated with an id    -> the conversation must belong to the caller (else 404).

The user message is committed *before* generation so it is never lost when the LLM fails; the
assistant message is then written as ``complete``/``refused``/``insufficient_evidence``/``failed``,
or ``incomplete`` when the client disconnects mid-stream.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.db.models import User
from app.graph.runner import PipelineResult, PipelineService, result_status
from app.graph.state import PipelineOptions
from app.services.conversations import ConversationService

logger = get_logger(__name__)


class ChatOutcome(BaseModel):
    result: PipelineResult
    status: str
    conversation_id: str | None
    message_id: str | None
    persisted: bool


class _Exchange:
    """Per-request persistence state."""

    def __init__(self, user: User | None, conversation_id: str | None) -> None:
        self.user = user
        self.conversation_id = conversation_id
        self.user_message_id: str | None = None
        self.assistant_message_id: str | None = None

    @property
    def persisting(self) -> bool:
        return self.user is not None and self.conversation_id is not None


class ChatService:
    def __init__(self, pipeline: PipelineService, conversations: ConversationService | None) -> None:
        self._pipeline = pipeline
        self._conversations = conversations

    # ------------------------------------------------------------------ helpers
    async def _begin(self, request_id: str, query: str, user: User | None, conversation_id: str | None) -> _Exchange:
        exchange = _Exchange(user, conversation_id)
        if user is None or self._conversations is None:
            exchange.conversation_id = conversation_id  # MEM-0 key only; nothing persisted
            exchange.user = None
            return exchange
        if conversation_id is None:
            conversation = await self._conversations.create(user, query)
            exchange.conversation_id = conversation.id
        else:
            await self._conversations.get(user, conversation_id)  # ownership check (404 otherwise)
        message = await self._conversations.add_message(
            user, exchange.conversation_id, role="user", content=query, request_id=request_id  # type: ignore[arg-type]
        )
        exchange.user_message_id = message.id
        return exchange

    async def _complete(self, exchange: _Exchange, request_id: str, result: PipelineResult, status: str) -> str | None:
        if not exchange.persisting:
            return None
        meta = result.metadata
        message = await self._conversations.add_message(  # type: ignore[union-attr]
            exchange.user, exchange.conversation_id, role="assistant", content=result.answer or "",  # type: ignore[arg-type]
            status=status, request_id=request_id,
            complexity=meta.complexity.complexity.value if meta.complexity else None,
            intent=meta.intent.intent.value if meta.intent else None,
            citations=result.citations,
        )
        return message.id

    async def _fail(self, exchange: _Exchange, request_id: str, exc: AppError, partial: str = "") -> None:
        if not exchange.persisting:
            return
        try:
            await self._conversations.add_message(  # type: ignore[union-attr]
                exchange.user, exchange.conversation_id, role="assistant",  # type: ignore[arg-type]
                content=partial or exc.public_message, status="failed", request_id=request_id,
            )
        except AppError as persist_exc:  # the original error matters more than the bookkeeping one
            logger.warning("could not persist failed assistant message", extra={"error_category": persist_exc.code})

    def _options(self, options: PipelineOptions, exchange: _Exchange) -> PipelineOptions:
        """Session memory key: user-scoped conversation (anonymous callers keep their client key)."""
        if exchange.user is not None and exchange.conversation_id:
            return options.model_copy(update={"session_key": f"{exchange.user.id}:{exchange.conversation_id}"})
        return options

    # ------------------------------------------------------------------ use cases
    async def ask(
        self, request_id: str, query: str, options: PipelineOptions, *, user: User | None, conversation_id: str | None
    ) -> ChatOutcome:
        exchange = await self._begin(request_id, query, user, conversation_id)
        try:
            result = await self._pipeline.run(request_id, query, self._options(options, exchange))
        except AppError as exc:
            await self._fail(exchange, request_id, exc)
            raise
        status = result_status(result)
        message_id = await self._complete(exchange, request_id, result, status)
        return ChatOutcome(result=result, status=status, conversation_id=exchange.conversation_id,
                           message_id=message_id, persisted=exchange.persisting)

    async def stream(
        self, request_id: str, query: str, options: PipelineOptions, *, user: User | None, conversation_id: str | None
    ) -> AsyncIterator[dict[str, Any]]:
        """Same events as the pipeline; ``start`` and ``complete`` carry conversation/message ids."""
        exchange = await self._begin(request_id, query, user, conversation_id)
        partial: list[str] = []
        finished = False
        try:
            async for event in self._pipeline.stream(request_id, query, self._options(options, exchange)):
                kind = event.get("type")
                if kind == "start":
                    yield {**event, "conversation_id": exchange.conversation_id, "persisted": exchange.persisting,
                           "user_message_id": exchange.user_message_id}
                    continue
                if kind == "token":
                    partial.append(event.get("content", ""))
                elif kind == "complete":
                    result = PipelineResult.model_validate({**event, "evidence": []})
                    status = event.get("status") or result_status(result)
                    message_id = await self._complete(exchange, request_id, result, status)
                    finished = True
                    yield {**event, "conversation_id": exchange.conversation_id, "message_id": message_id,
                           "persisted": exchange.persisting}
                    continue
                elif kind == "error":
                    finished = True
                    if exchange.persisting:
                        await self._fail(exchange, request_id, AppError(public_message=event.get("message", "failed")),
                                         "".join(partial))
                yield event
        except asyncio.CancelledError:
            # Client disconnected: keep what was streamed, marked incomplete, then propagate.
            if not finished and exchange.persisting:
                await asyncio.shield(self._mark_incomplete(exchange, request_id, "".join(partial)))
            raise
        except AppError as exc:
            await self._fail(exchange, request_id, exc, "".join(partial))
            yield {"type": "error", "code": exc.code, "message": exc.public_message, "request_id": request_id}

    async def _mark_incomplete(self, exchange: _Exchange, request_id: str, partial: str) -> None:
        try:
            await self._conversations.add_message(  # type: ignore[union-attr]
                exchange.user, exchange.conversation_id, role="assistant", content=partial,  # type: ignore[arg-type]
                status="incomplete", request_id=request_id,
            )
        except AppError as exc:
            logger.warning("could not persist incomplete assistant message", extra={"error_category": exc.code})
