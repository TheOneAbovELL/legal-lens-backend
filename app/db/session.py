"""Async database engine/session management and programmatic migrations."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import PROJECT_ROOT


class Database:
    def __init__(self, url: str) -> None:
        parsed = make_url(url)
        if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:"):
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        self.url = url
        self.engine: AsyncEngine = create_async_engine(url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            yield session

    async def ping(self) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def migrate(self) -> None:
        """Run Alembic migrations to head (in a worker thread; Alembic drives its own loop)."""
        from alembic import command
        from alembic.config import Config

        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", self.url.replace("%", "%%"))
        await asyncio.to_thread(command.upgrade, config, "head")

    async def close(self) -> None:
        await self.engine.dispose()
