"""Factory that builds the configured LLM from application settings."""

from __future__ import annotations

from typing import Any

from pydantic import SecretStr

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger
from app.integrations.llm.base import BaseLLM
from app.integrations.llm.providers import LangChainLLM

logger = get_logger(__name__)


def _build_chat_model(settings: Settings) -> Any:
    """Instantiate the LangChain chat model for the configured provider."""
    provider = settings.llm_provider
    api_key = settings.resolved_llm_api_key()
    if not api_key:
        raise ConfigurationError(
            f"No API key configured for LLM provider '{provider}'. "
            "Set LLM_API_KEY (or the provider specific variable)."
        )
    secret = SecretStr(api_key)

    common: dict[str, Any] = {
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "timeout": settings.llm_timeout,
        "max_retries": settings.llm_max_retries,
    }

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(api_key=secret, **common)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(api_key=secret, **common)
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(google_api_key=secret, **common)

    raise ConfigurationError(f"Unsupported LLM provider: {provider}")


def build_llm(settings: Settings) -> BaseLLM:
    """Return a ready-to-use :class:`BaseLLM` for the configured provider."""
    chat_model = _build_chat_model(settings)
    logger.info(
        "LLM configured", extra={"provider": settings.llm_provider, "model": settings.llm_model}
    )
    return LangChainLLM(
        provider=settings.llm_provider,
        model=settings.llm_model,
        chat_model=chat_model,
        timeout=settings.llm_timeout,
    )
