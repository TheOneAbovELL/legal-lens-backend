"""Conversation use cases: ownership-scoped history persistence (no RAG logic here)."""

from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.db.models import Conversation, Message, MessageEvidence, User
from app.db.repositories import ConversationRepository
from app.db.session import Database
from app.domain.retrieval import Citation

TITLE_MAX_CHARS = 80
_NOT_FOUND = "Conversation not found."


def title_from_query(query: str) -> str:
    text = " ".join(query.split())
    if len(text) <= TITLE_MAX_CHARS:
        return text or "New conversation"
    cut = text[:TITLE_MAX_CHARS]
    return (cut[: cut.rfind(" ")] if " " in cut else cut).rstrip(" ,.;:") + "…"


def evidence_rows(citations: list[Citation]) -> list[MessageEvidence]:
    return [
        MessageEvidence(
            citation_id=c.citation_id, document_id=c.document_id, chunk_id=c.chunk_id, source=c.source,
            title=c.title, act=c.act, section=c.section, page=c.page, excerpt=c.excerpt, score=c.score,
        )
        for c in citations
    ]


class ConversationService:
    """Every method takes the acting user; a conversation owned by someone else is a 404 (never 403:
    the existence of another user's conversation must not leak)."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def create(self, user: User, title: str | None) -> Conversation:
        async with self._database.sessions() as session:
            return await ConversationRepository(session).create(user_id=user.id, title=title_from_query(title or ""))

    async def list(self, user: User, *, limit: int = 100) -> list[Conversation]:
        async with self._database.sessions() as session:
            return await ConversationRepository(session).list(user_id=user.id, limit=limit)

    async def get(self, user: User, conversation_id: str, *, with_messages: bool = False) -> Conversation:
        async with self._database.sessions() as session:
            conversation = await ConversationRepository(session).get(
                user_id=user.id, conversation_id=conversation_id, with_messages=with_messages
            )
        if conversation is None:
            raise NotFoundError("conversation not found or not owned", public_message=_NOT_FOUND)
        return conversation

    async def message_count(self, conversation_id: str) -> int:
        async with self._database.sessions() as session:
            return await ConversationRepository(session).message_count(conversation_id=conversation_id)

    async def rename(self, user: User, conversation_id: str, title: str) -> Conversation:
        async with self._database.sessions() as session:
            conversation = await ConversationRepository(session).rename(
                user_id=user.id, conversation_id=conversation_id, title=title
            )
        if conversation is None:
            raise NotFoundError("conversation not found or not owned", public_message=_NOT_FOUND)
        return conversation

    async def delete(self, user: User, conversation_id: str) -> None:
        async with self._database.sessions() as session:
            deleted = await ConversationRepository(session).delete(user_id=user.id, conversation_id=conversation_id)
        if not deleted:
            raise NotFoundError("conversation not found or not owned", public_message=_NOT_FOUND)

    async def add_message(
        self,
        user: User,
        conversation_id: str,
        *,
        role: str,
        content: str,
        status: str = "complete",
        request_id: str | None = None,
        complexity: str | None = None,
        intent: str | None = None,
        citations: list[Citation] | None = None,
    ) -> Message:
        async with self._database.sessions() as session:
            message = await ConversationRepository(session).add_message(
                user_id=user.id, conversation_id=conversation_id, role=role, content=content, status=status,
                request_id=request_id, complexity=complexity, intent=intent, evidence=evidence_rows(citations or []),
            )
        if message is None:
            raise NotFoundError("conversation not found or not owned", public_message=_NOT_FOUND)
        return message

    async def update_message(self, message_id: str, *, content: str, status: str) -> None:
        async with self._database.sessions() as session:
            await ConversationRepository(session).update_message(message_id=message_id, content=content, status=status)
