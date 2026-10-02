"""LLM provider interface. Business logic depends on this, never on a vendor SDK."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.retrieval import TokenUsage


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMRequest(BaseModel):
    messages: list[ChatMessage]
    temperature: float = 0.1
    max_tokens: int = 1024
    json_mode: bool = False
    timeout: float | None = None


class LLMResponse(BaseModel):
    text: str
    provider: str
    model: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    attempts: int = 1


class StreamChunk(BaseModel):
    """Either a text delta or (final chunk) usage information."""

    delta: str = ""
    usage: TokenUsage | None = None


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Single, non-streaming completion."""

    @abstractmethod
    def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        """Real token streaming from the provider."""

    @property
    def configured(self) -> bool:
        return True

    async def aclose(self) -> None:  # pragma: no cover - default no-op
        return None
