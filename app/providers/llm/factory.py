"""Build the configured provider chain."""

from __future__ import annotations

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.providers.llm.base import LLMProvider
from app.providers.llm.groq_provider import GroqProvider
from app.providers.llm.router import LLMRouter


def build_provider(name: str, model: str, settings: Settings) -> LLMProvider:
    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    if name == "groq":
        reasoning = any(model.startswith(prefix) for prefix in settings.llm_reasoning_model_prefixes)
        return GroqProvider(api_key=api_key, model=model, timeout=settings.llm_timeout, reasoning=reasoning,
                            reasoning_effort=settings.llm_reasoning_effort)
    raise ConfigurationError(f"unsupported LLM provider {name!r}; supported: groq")


def build_llm_router(settings: Settings) -> LLMRouter:
    try:
        targets = settings.llm_targets
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc
    providers = [build_provider(name, model, settings) for name, model in targets]
    return LLMRouter(
        providers,
        retry_enabled=settings.llm_retry_enabled,
        max_retries=settings.llm_max_retries,
        backoff=settings.llm_backoff,
        backoff_max=settings.llm_backoff_max,
    )
