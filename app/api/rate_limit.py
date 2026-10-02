"""In-process sliding-window rate limiter (bounded memory).

Limits are per process: behind several workers/instances the effective limit multiplies. Swap in
a shared store (e.g. Redis) if strict global limits become a requirement.
"""

from __future__ import annotations

import time
from collections import OrderedDict, deque


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int, max_clients: int = 10_000) -> None:
        self._limit = limit
        self._window = window_seconds
        self._max_clients = max_clients
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    def check(self, key: str) -> tuple[bool, int]:
        """Record a hit; return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        hits = self._hits.get(key)
        if hits is None:
            hits = deque()
            self._hits[key] = hits
        self._hits.move_to_end(key)
        while hits and now - hits[0] >= self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            return False, max(1, int(self._window - (now - hits[0])) + 1)
        hits.append(now)
        while len(self._hits) > self._max_clients:
            self._hits.popitem(last=False)
        return True, 0
