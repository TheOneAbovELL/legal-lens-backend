"""Bounded async retry with exponential backoff and full jitter."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.core.logging import get_logger

T = TypeVar("T")
logger = get_logger(__name__)


def backoff_delay(attempt: int, base: float, cap: float) -> float:
    """Full-jitter exponential backoff (attempt starts at 1)."""
    if base <= 0:
        return 0.0
    return random.uniform(0, min(cap, base * (2 ** (attempt - 1))))  # noqa: S311 - jitter, not crypto


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    retries: int,
    is_retryable: Callable[[BaseException], bool],
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    operation_name: str = "operation",
) -> T:
    """Run ``operation`` with at most ``retries`` additional attempts on retryable errors."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return await operation()
        except Exception as exc:
            if attempt > retries or not is_retryable(exc):
                raise
            delay = backoff_delay(attempt, base_delay, max_delay)
            logger.warning(
                "retrying after failure",
                extra={"operation": operation_name, "attempt": attempt, "delay_s": round(delay, 3),
                       "error_type": type(exc).__name__},
            )
            await asyncio.sleep(delay)
