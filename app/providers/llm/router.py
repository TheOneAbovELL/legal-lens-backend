"""Retry + fallback router over an ordered list of LLM providers.

Policy:
* each provider gets ``1 + max_retries`` attempts for *retryable* errors (timeouts, 429, 5xx),
  with exponential backoff + full jitter between attempts;
* permanent errors (400/401/403/404/422, missing key) are not retried and fall through to the
  next provider immediately;
* streaming only retries/falls back while no token has been emitted — once text reached the
  client, a mid-stream failure is surfaced instead of silently restarting the answer.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.core.exceptions import LLMProviderError
from app.core.logging import get_logger
from app.core.retry import backoff_delay
from app.providers.llm.base import LLMProvider, LLMRequest, LLMResponse, StreamChunk

logger = get_logger(__name__)


class StreamOrigin(StreamChunk):
    """First chunk of a stream announcing which provider/model is answering."""

    provider: str
    model: str
    attempts: int


class LLMRouter:
    def __init__(
        self,
        providers: list[LLMProvider],
        *,
        retry_enabled: bool = True,
        max_retries: int = 2,
        backoff: float = 0.5,
        backoff_max: float = 8.0,
    ) -> None:
        if not providers:
            raise ValueError("LLMRouter requires at least one provider")
        self.providers = providers
        self._max_retries = max_retries if retry_enabled else 0
        self._backoff = backoff
        self._backoff_max = backoff_max

    @property
    def configured(self) -> bool:
        return any(p.configured for p in self.providers)

    @property
    def primary(self) -> LLMProvider:
        return self.providers[0]

    async def _sleep(self, attempt: int) -> None:
        await asyncio.sleep(backoff_delay(attempt, self._backoff, self._backoff_max))

    def _log_failure(self, provider: LLMProvider, attempt: int, exc: LLMProviderError) -> None:
        logger.warning(
            "llm attempt failed",
            extra={
                "provider": provider.name,
                "model": provider.model,
                "attempt": attempt,
                "retryable": exc.retryable,
                "status_code": exc.status_code,
                "error_category": exc.code,
            },
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        failures: list[str] = []
        total_attempts = 0
        for provider in self.providers:
            for attempt in range(1, self._max_retries + 2):
                total_attempts += 1
                try:
                    response = await provider.complete(request)
                    response.attempts = total_attempts
                    return response
                except LLMProviderError as exc:
                    self._log_failure(provider, attempt, exc)
                    failures.append(f"{provider.name}:{provider.model}#{attempt}:{exc}")
                    if not exc.retryable or attempt > self._max_retries:
                        break
                    await self._sleep(attempt)
        raise LLMProviderError("all LLM providers failed: " + "; ".join(failures), retryable=False)

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        failures: list[str] = []
        total_attempts = 0
        for provider in self.providers:
            for attempt in range(1, self._max_retries + 2):
                total_attempts += 1
                emitted = False
                try:
                    async for chunk in provider.stream(request):
                        if not emitted:
                            emitted = True
                            yield StreamOrigin(provider=provider.name, model=provider.model, attempts=total_attempts)
                        yield chunk
                    if not emitted:  # empty but successful stream
                        yield StreamOrigin(provider=provider.name, model=provider.model, attempts=total_attempts)
                    return
                except LLMProviderError as exc:
                    self._log_failure(provider, attempt, exc)
                    if emitted:
                        raise LLMProviderError(
                            f"stream interrupted after output started: {exc}", provider=provider.name
                        ) from exc
                    failures.append(f"{provider.name}:{provider.model}#{attempt}:{exc}")
                    if not exc.retryable or attempt > self._max_retries:
                        break
                    await self._sleep(attempt)
        raise LLMProviderError("all LLM providers failed: " + "; ".join(failures), retryable=False)

    async def aclose(self) -> None:
        for provider in self.providers:
            await provider.aclose()
