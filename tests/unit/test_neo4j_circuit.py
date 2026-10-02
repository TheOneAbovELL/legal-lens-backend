from __future__ import annotations

import time

import pytest

from app.core.exceptions import RetrievalError
from app.providers.graph_db.neo4j_client import Neo4jClient


class _SlowDriver:
    def __init__(self) -> None:
        self.calls = 0

    async def execute_query(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        import asyncio

        self.calls += 1
        await asyncio.sleep(10)

    async def close(self) -> None:
        return None


async def test_unreachable_graph_times_out_once_then_fails_fast() -> None:
    client = Neo4jClient("neo4j://127.0.0.1:1", "u", "p", timeout=0.2, cooldown=60)
    await client._driver.close()
    driver = _SlowDriver()
    client._driver = driver  # type: ignore[assignment]
    start = time.monotonic()
    with pytest.raises(RetrievalError):
        await client.statutes([("IPC", "420")])
    assert time.monotonic() - start < 2 and client.circuit_open
    start = time.monotonic()
    for _ in range(5):
        with pytest.raises(RetrievalError, match="circuit open"):
            await client.statutes([("IPC", "420")])
    assert time.monotonic() - start < 0.1  # no further timeouts while the circuit is open
    assert driver.calls == 1
