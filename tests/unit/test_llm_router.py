from __future__ import annotations

import pytest

from app.core.exceptions import EmbeddingError, LLMProviderError
from app.providers.embeddings.base import validate_vectors
from app.providers.llm.base import ChatMessage, LLMRequest
from app.providers.llm.groq_provider import GroqProvider
from app.providers.llm.router import LLMRouter, StreamOrigin
from tests.fakes import HashingEmbedder, ScriptedLLM

REQ = LLMRequest(messages=[ChatMessage(role="user", content="hi")])


def transient() -> LLMProviderError:
    return LLMProviderError("503", provider="fake", status_code=503, retryable=True)


def permanent() -> LLMProviderError:
    return LLMProviderError("401", provider="fake", status_code=401, retryable=False)


async def test_retries_transient_then_succeeds() -> None:
    primary = ScriptedLLM(["ok"], failures=[transient()])
    response = await LLMRouter([primary], max_retries=2, backoff=0).complete(REQ)
    assert response.text == "ok" and response.attempts == 2


async def test_permanent_error_falls_back_without_retry() -> None:
    primary = ScriptedLLM(["never"], name="a", failures=[permanent(), permanent()])
    secondary = ScriptedLLM(["from b"], name="b")
    response = await LLMRouter([primary, secondary], max_retries=3, backoff=0).complete(REQ)
    assert response.provider == "b"
    assert len(primary.requests) == 1  # 401 is not retried


async def test_retry_budget_is_bounded() -> None:
    primary = ScriptedLLM(["x"], failures=[transient() for _ in range(10)])
    with pytest.raises(LLMProviderError, match="all LLM providers failed"):
        await LLMRouter([primary], max_retries=2, backoff=0).complete(REQ)
    assert len(primary.requests) == 3


async def test_stream_falls_back_before_first_token_and_reports_origin() -> None:
    primary = ScriptedLLM(["x"], name="a", failures=[permanent()])
    secondary = ScriptedLLM(["hello world"], name="b")
    chunks = [c async for c in LLMRouter([primary, secondary], max_retries=0, backoff=0).stream(REQ)]
    origin = chunks[0]
    assert isinstance(origin, StreamOrigin) and origin.provider == "b"
    assert "".join(c.delta for c in chunks[1:]) == "hello world"


async def test_retry_disabled() -> None:
    primary = ScriptedLLM(["x"], failures=[transient()])
    with pytest.raises(LLMProviderError):
        await LLMRouter([primary], retry_enabled=False, max_retries=5, backoff=0).complete(REQ)
    assert len(primary.requests) == 1


async def test_groq_provider_without_key_is_unconfigured() -> None:
    provider = GroqProvider(api_key=None, model="m", timeout=1)
    assert not provider.configured
    with pytest.raises(LLMProviderError) as exc:
        await provider.complete(REQ)
    assert exc.value.retryable is False


def test_embedding_validation_rejects_zero_and_bad_dims() -> None:
    with pytest.raises(EmbeddingError):
        validate_vectors([[0.0, 0.0]], 1, 2)
    with pytest.raises(EmbeddingError):
        validate_vectors([[1.0]], 1, 2)
    with pytest.raises(EmbeddingError):
        validate_vectors([[float("nan"), 1.0]], 1, 2)
    validate_vectors([[0.6, 0.8]], 1, 2)


async def test_embedder_failure_raises_not_zero_vectors() -> None:
    with pytest.raises(EmbeddingError):
        await HashingEmbedder(fail=True).embed_query("x")


def test_groq_reasoning_params_only_for_reasoning_models() -> None:
    from app.core.config import Settings
    from app.providers.llm.factory import build_provider

    settings = Settings(_env_file=None, llm_api_key="k")  # type: ignore[call-arg]
    reasoning = build_provider("groq", "openai/gpt-oss-20b", settings)._kwargs(REQ)  # type: ignore[attr-defined]
    assert reasoning["include_reasoning"] is False and reasoning["reasoning_effort"] == "low"
    plain = build_provider("groq", "some-other-model", settings)._kwargs(REQ)  # type: ignore[attr-defined]
    assert "include_reasoning" not in plain and "reasoning_effort" not in plain
