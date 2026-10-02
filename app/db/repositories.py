"""Data access for users."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.db.models import User


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
