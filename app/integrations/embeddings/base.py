"""Provider-agnostic embedding interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class EmbeddingHealth(BaseModel):
    """Result of an embedding provider reachability probe."""

    reachable: bool
    detail: str | None = None


class BaseEmbeddings(ABC):
    """Interface every embedding provider must implement."""

    provider: str
    model: str
    dimension: int

    @abstractmethod
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents."""

    @abstractmethod
    async def aembed_query(self, text: str) -> list[float]:
        """Embed a single query string."""

    @abstractmethod
    async def health_check(self) -> EmbeddingHealth:
        """Perform a real, cheap embedding call to confirm reachability."""
