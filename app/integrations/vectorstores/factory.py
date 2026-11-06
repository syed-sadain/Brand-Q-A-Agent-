"""Factory that builds the configured vector store backend."""

from __future__ import annotations

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger
from app.integrations.vectorstores.base import BaseVectorStore
from app.integrations.vectorstores.memory_store import InMemoryVectorStore

logger = get_logger(__name__)


def build_vector_store(settings: Settings) -> BaseVectorStore:
    """Return the vector store selected by ``VECTOR_STORE_PROVIDER``."""
    provider = settings.vector_store_provider

    if provider == "pinecone":
        from app.integrations.vectorstores.pinecone_store import PineconeVectorStore

        store: BaseVectorStore = PineconeVectorStore(settings)
    elif provider == "chroma":
        from app.integrations.vectorstores.chroma_store import ChromaVectorStore

        store = ChromaVectorStore(settings)
    elif provider == "memory":
        store = InMemoryVectorStore(dimension=settings.embedding_dimension)
    else:  # pragma: no cover - Literal already constrains this
        raise ConfigurationError(f"Unsupported vector store provider: {provider}")

    logger.info(
        "vector store configured", extra={"provider": provider, "dimension": store.dimension}
    )
    return store
