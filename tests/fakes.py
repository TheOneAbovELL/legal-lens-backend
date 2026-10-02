"""Test doubles for external services. Used only by the test suite — never by the application."""

from __future__ import annotations

import math
import re
import zlib
from collections.abc import AsyncIterator, Sequence

from app.core.exceptions import EmbeddingError, LLMProviderError
from app.domain.retrieval import TokenUsage
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.llm.base import LLMProvider, LLMRequest, LLMResponse, StreamChunk

_WORD = re.compile(r"[a-z0-9]+")


class HashingEmbedder(EmbeddingProvider):
    """Deterministic bag-of-words hashing embedder: similar wording -> similar vectors.

    Good enough to exercise retrieval mechanics in tests without downloading a model.
    """

    def __init__(self, dimension: int = 64, *, fail: bool = False) -> None:
        self.model_name = "test-hashing-embedder"
        self.model_version = "test"
        self.dimension = dimension
        self.fail = fail
        self.calls = 0

    @property
    def is_ready(self) -> bool:
        return True

    async def warmup(self) -> None:
        return None

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        for word in _WORD.findall(text.lower()):
            vec[zlib.crc32(word.encode()) % self.dimension] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            vec[0], norm = 1.0, 1.0
        return [v / norm for v in vec]

    async def embed_query(self, text: str) -> list[float]:
        self.calls += 1
        if self.fail:
            raise EmbeddingError("embedder failure (test)")
        return self._vector(text)

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail:
            raise EmbeddingError("embedder failure (test)")
        return [self._vector(t) for t in texts]


class ScriptedLLM(LLMProvider):
    """LLM provider returning scripted answers; can fail a set number of times."""

    def __init__(
        self,
        answers: list[str] | None = None,
        *,
        name: str = "fake",
        model: str = "fake-model",
        failures: list[LLMProviderError] | None = None,
        json_answer: str | None = None,
        configured: bool = True,
    ) -> None:
        self.name = name
        self.model = model
        self._answers = list(answers or ["Answer grounded in evidence [C1]."])
        self._failures = list(failures or [])
        self._json_answer = json_answer
        self._configured = configured
        self.requests: list[LLMRequest] = []

    @property
    def configured(self) -> bool:
        return self._configured

    def _next(self, request: LLMRequest) -> str:
        self.requests.append(request)
        if self._failures:
            raise self._failures.pop(0)
        if request.json_mode and self._json_answer is not None:
            return self._json_answer
        return self._answers.pop(0) if len(self._answers) > 1 else self._answers[0]

    async def complete(self, request: LLMRequest) -> LLMResponse:
        text = self._next(request)
        return LLMResponse(text=text, provider=self.name, model=self.model,
                           usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15))

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        text = self._next(request)
        for piece in re.findall(r"\S+\s*", text):
            yield StreamChunk(delta=piece)
        yield StreamChunk(usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15))
