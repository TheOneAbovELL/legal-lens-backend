"""Groq LLM provider (OpenAI-compatible chat completions with real streaming)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import groq

from app.core.exceptions import LLMProviderError
from app.domain.retrieval import TokenUsage
from app.providers.llm.base import LLMProvider, LLMRequest, LLMResponse, StreamChunk

_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def _translate(exc: Exception, model: str) -> LLMProviderError:
    """Map SDK exceptions to LLMProviderError with a retryability verdict. Never include keys."""
    if isinstance(exc, groq.APITimeoutError):
        return LLMProviderError(f"groq timeout ({model})", provider="groq", retryable=True)
    if isinstance(exc, groq.APIConnectionError):
        return LLMProviderError(f"groq connection error ({model})", provider="groq", retryable=True)
    if isinstance(exc, groq.APIStatusError):
        status = exc.status_code
        return LLMProviderError(
            f"groq HTTP {status} ({model}): {type(exc).__name__}",
            provider="groq",
            status_code=status,
            retryable=status in _RETRYABLE_STATUS,
        )
    return LLMProviderError(f"groq unexpected error ({model}): {type(exc).__name__}", provider="groq")


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(
        self, *, api_key: str | None, model: str, timeout: float,
        reasoning: bool = False, reasoning_effort: str | None = None,
    ) -> None:
        self.model = model
        self._reasoning = reasoning
        self._reasoning_effort = reasoning_effort
        self._timeout = timeout
        self._api_key = api_key
        # SDK-level retries disabled: retry/fallback policy lives in LLMRouter.
        self._client = groq.AsyncGroq(api_key=api_key, timeout=timeout, max_retries=0) if api_key else None

    @property
    def configured(self) -> bool:
        return self._client is not None

    def _require_client(self) -> groq.AsyncGroq:
        if self._client is None:
            raise LLMProviderError("GROQ/LLM API key is not configured", provider="groq", retryable=False)
        return self._client

    def _kwargs(self, request: LLMRequest) -> dict:
        kwargs: dict = {
            "model": self.model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "timeout": request.timeout or self._timeout,
        }
        if request.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if self._reasoning:
            # Never return hidden reasoning; bound its cost so the answer gets the token budget.
            kwargs["include_reasoning"] = False
            if self._reasoning_effort:
                kwargs["reasoning_effort"] = self._reasoning_effort
        return kwargs

    async def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._require_client()
        try:
            response = await client.chat.completions.create(**self._kwargs(request))
        except groq.GroqError as exc:
            raise _translate(exc, self.model) from exc
        if not response.choices:
            raise LLMProviderError("groq returned no choices", provider="groq", retryable=True)
        usage = response.usage
        return LLMResponse(
            text=response.choices[0].message.content or "",
            provider=self.name,
            model=self.model,
            usage=TokenUsage(
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
            ),
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        client = self._require_client()
        try:
            stream = await client.chat.completions.create(**self._kwargs(request), stream=True)
            async for event in stream:
                if event.choices:
                    delta = event.choices[0].delta.content
                    if delta:
                        yield StreamChunk(delta=delta)
                x_groq = getattr(event, "x_groq", None)
                usage = getattr(x_groq, "usage", None) if x_groq else None
                if usage is not None:
                    yield StreamChunk(
                        usage=TokenUsage(
                            prompt_tokens=getattr(usage, "prompt_tokens", None),
                            completion_tokens=getattr(usage, "completion_tokens", None),
                            total_tokens=getattr(usage, "total_tokens", None),
                        )
                    )
        except groq.GroqError as exc:
            raise _translate(exc, self.model) from exc

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
