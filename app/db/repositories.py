"""Data access. Every conversation/message query is scoped by the owning user id."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError
from app.db.models import Conversation, Message, MessageEvidence, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: str) -> User | None:
        return await self._session.get(User, user_id)

    async def by_login(self, login: str) -> User | None:
        login = login.strip().lower()
        result = await self._session.execute(
            select(User).where(or_(func.lower(User.username) == login, func.lower(User.email) == login))
        )
        return result.scalars().first()

    async def create(self, *, username: str, email: str | None, password_hash: str, role: str) -> User:
        user = User(username=username, email=email, password_hash=password_hash, role=role)
        self._session.add(user)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("username or email already registered",
                                public_message="Username or email is already registered.") from exc
        await self._session.refresh(user)
        return user


class ConversationRepository:
    """Conversations and messages. ``user_id`` is mandatory on every read and write."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: str, title: str) -> Conversation:
        conversation = Conversation(user_id=user_id, title=title)
        self._session.add(conversation)
        await self._session.commit()
        await self._session.refresh(conversation)
        return conversation

    async def list(self, *, user_id: str, limit: int = 100, include_archived: bool = False) -> list[Conversation]:
        stmt = select(Conversation).where(Conversation.user_id == user_id)
        if not include_archived:
            stmt = stmt.where(Conversation.archived_at.is_(None))
        stmt = stmt.order_by(Conversation.updated_at.desc()).limit(limit)
        return list((await self._session.execute(stmt)).scalars().all())

    async def get(self, *, user_id: str, conversation_id: str, with_messages: bool = False) -> Conversation | None:
        stmt = select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        if with_messages:
            stmt = stmt.options(selectinload(Conversation.messages).selectinload(Message.evidence))
        return (await self._session.execute(stmt)).scalars().first()

    async def message_count(self, *, conversation_id: str) -> int:
        stmt = select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
        return int((await self._session.execute(stmt)).scalar_one())

    async def rename(self, *, user_id: str, conversation_id: str, title: str) -> Conversation | None:
        conversation = await self.get(user_id=user_id, conversation_id=conversation_id)
        if conversation is None:
            return None
        conversation.title = title
        await self._session.commit()
        await self._session.refresh(conversation)
        return conversation

    async def delete(self, *, user_id: str, conversation_id: str) -> bool:
        conversation = await self.get(user_id=user_id, conversation_id=conversation_id)
        if conversation is None:
            return False
        await self._session.delete(conversation)
        await self._session.commit()
        return True

    async def add_message(
        self,
        *,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
        status: str = "complete",
        request_id: str | None = None,
        complexity: str | None = None,
        intent: str | None = None,
        evidence: list[MessageEvidence] | None = None,
    ) -> Message | None:
        conversation = await self.get(user_id=user_id, conversation_id=conversation_id)
        if conversation is None:
            return None
        message = Message(conversation_id=conversation_id, role=role, content=content, status=status,
                          request_id=request_id, complexity=complexity, intent=intent)
        for position, item in enumerate(evidence or []):
            item.position = position
            message.evidence.append(item)
        self._session.add(message)
        await self._session.execute(
            update(Conversation).where(Conversation.id == conversation_id).values(updated_at=datetime.now(UTC))
        )
        await self._session.commit()
        await self._session.refresh(message, attribute_names=["evidence"])
        return message

    async def update_message(self, *, message_id: str, content: str, status: str) -> None:
        await self._session.execute(update(Message).where(Message.id == message_id).values(content=content, status=status))
        await self._session.commit()
