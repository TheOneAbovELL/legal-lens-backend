from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import redact


def test_defaults_use_embedded_qdrant_when_no_url() -> None:
    s = Settings(_env_file=None, qdrant_url=None)  # type: ignore[call-arg]
    assert s.qdrant_path and s.qdrant_path.endswith("qdrant")


def test_groq_api_key_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_testvalue123456")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.llm_api_key is not None and s.llm_api_key.get_secret_value() == "gsk_testvalue123456"
    assert "gsk_testvalue123456" not in repr(s)  # secrets never appear in reprs


def test_provider_order_parsing() -> None:
    s = Settings(_env_file=None, llm_provider_order="groq:a, groq:b")  # type: ignore[call-arg]
    assert s.llm_targets == [("groq", "a"), ("groq", "b")]
    with pytest.raises(ValueError):
        _ = Settings(_env_file=None, llm_provider_order="groq").llm_targets  # type: ignore[call-arg]


def test_production_requires_strong_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", jwt_secret_key="short")  # type: ignore[call-arg]
    ok = Settings(_env_file=None, app_env="production", jwt_secret_key="x" * 40)  # type: ignore[call-arg]
    assert ok.is_production


def test_cors_csv_parsing() -> None:
    s = Settings(_env_file=None, cors_origins="https://a.example, https://b.example")  # type: ignore[call-arg]
    assert s.cors_origins == ["https://a.example", "https://b.example"]


def test_secret_redaction() -> None:
    text = redact("key gsk_abcdefghijklmnop and Bearer abcdefghijklmnop password=hunter22")
    assert "gsk_abcdefghijklmnop" not in text
    assert "abcdefghijklmnop" not in text
    assert "hunter22" not in text
