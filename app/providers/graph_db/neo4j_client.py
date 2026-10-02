"""Async Neo4j client for the legal knowledge graph.

Schema (per the Legal Lens system design):
    (:Statute {code, section, title, text?, is_active?})
    (:Statute)-[:REPLACED_BY {effective_date?, modification_type?}]->(:Statute)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app.core.exceptions import RetrievalError
from app.core.logging import get_logger

logger = get_logger(__name__)

_STATUTES_QUERY = """
UNWIND $refs AS ref
MATCH (s:Statute)
WHERE toUpper(s.code) = ref.code AND toString(s.section) = ref.section
RETURN s.code AS code, toString(s.section) AS section, s.title AS title, s.text AS text,
       s.is_active AS is_active
LIMIT $limit
"""

_REPLACEMENTS_QUERY = """
MATCH (old:Statute)-[r:REPLACED_BY]->(new:Statute)
WHERE toUpper(old.code) = $code AND toString(old.section) = $section
RETURN new.code AS code, toString(new.section) AS section, new.title AS title,
       toString(r.effective_date) AS effective_date, r.modification_type AS modification_type
"""

_REPLACED_FROM_QUERY = """
MATCH (old:Statute)-[r:REPLACED_BY]->(new:Statute)
WHERE toUpper(new.code) = $code AND toString(new.section) = $section
RETURN old.code AS code, toString(old.section) AS section, old.title AS title,
       toString(r.effective_date) AS effective_date, r.modification_type AS modification_type
"""


class Neo4jClient:
    """Optional dependency: a hard per-call timeout plus a circuit breaker, so an unreachable
    graph costs one timeout per cooldown window instead of one per query."""

    def __init__(self, uri: str, user: str, password: str, *, timeout: float = 5.0, cooldown: float = 60.0) -> None:
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(
            uri, auth=(user, password), connection_timeout=timeout, max_transaction_retry_time=timeout
        )
        self._timeout = timeout
        self._cooldown = cooldown
        self._open_until = 0.0

    @property
    def circuit_open(self) -> bool:
        return time.monotonic() < self._open_until

    async def _run(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        if self.circuit_open:
            raise RetrievalError("neo4j circuit open (recent failure); skipping")
        try:
            records, _, _ = await asyncio.wait_for(
                self._driver.execute_query(cypher, parameters_=params, routing_="r"), timeout=self._timeout
            )
        except (Neo4jError, ServiceUnavailable, OSError, TimeoutError) as exc:
            self._open_until = time.monotonic() + self._cooldown
            logger.warning("neo4j unavailable; circuit opened", extra={"cooldown_s": self._cooldown,
                                                                         "error_type": type(exc).__name__})
            raise RetrievalError(f"neo4j query failed: {type(exc).__name__}") from exc
        self._open_until = 0.0
        return [record.data() for record in records]

    async def statutes(self, refs: list[tuple[str, str]], limit: int = 10) -> list[dict[str, Any]]:
        if not refs:
            return []
        payload = [{"code": code.upper(), "section": section} for code, section in refs]
        return await self._run(_STATUTES_QUERY, refs=payload, limit=limit)

    async def replacements(self, code: str, section: str) -> list[dict[str, Any]]:
        return await self._run(_REPLACEMENTS_QUERY, code=code.upper(), section=section)

    async def replaced_from(self, code: str, section: str) -> list[dict[str, Any]]:
        return await self._run(_REPLACED_FROM_QUERY, code=code.upper(), section=section)

    async def verify(self) -> None:
        try:
            await asyncio.wait_for(self._driver.verify_connectivity(), timeout=self._timeout)
        except (Neo4jError, ServiceUnavailable, OSError, TimeoutError) as exc:
            raise RetrievalError(f"neo4j unreachable: {type(exc).__name__}") from exc

    async def close(self) -> None:
        await self._driver.close()
