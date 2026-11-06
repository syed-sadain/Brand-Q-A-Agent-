"""Factory that builds the configured embedding provider."""

from __future__ import annotations

from typing import Any

from pydantic import SecretStr

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger
from app.integrations.embeddings.base import BaseEmbeddings
from app.integrations.embeddings.providers import HashingEmbeddings, LangChainEmbeddings

logger = get_logger(__name__)


def build_embeddings(settings: Settings) -> BaseEmbeddings:
    """Return the configured embedding provider.

    ``hashing`` is a deterministic, offline embedding used for local development
    and tests. ``openai`` and ``google`` use the real provider SDKs.
    """
    provider = settings.embedding_provider

    if provider == "hashing":
        logger.info("embeddings configured", extra={"provider": provider, "model": "hashing"})
        return HashingEmbeddings(dimension=settings.embedding_dimension)

    api_key = settings.resolved_embedding_api_key()
    if not api_key:
        raise ConfigurationError(
            f"No API key configured for embedding provider '{provider}'. "
            "Set EMBEDDING_API_KEY (or the provider specific variable)."
        )
    secret = SecretStr(api_key)
    embeddings: Any

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        embeddings = OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=secret,
            dimensions=settings.embedding_dimension,
        )
    elif provider == "google":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        embeddings = GoogleGenerativeAIEmbeddings(
            model=settings.embedding_model,
            google_api_key=secret,
        )
    else:  # pragma: no cover - Literal already constrains this
        raise ConfigurationError(f"Unsupported embedding provider: {provider}")

    logger.info(
        "embeddings configured", extra={"provider": provider, "model": settings.embedding_model}
    )
    return LangChainEmbeddings(
        provider=provider,
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
        embeddings=embeddings,
    )
