"""Vector store abstraction.

Business logic depends only on :class:`BaseVectorStore`; concrete adapters
(Pinecone, Chroma, in-memory) are swappable through the factory. Tenant
isolation is enforced here via mandatory namespaces, not in route handlers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field

VectorStoreStatus = Literal["healthy", "degraded", "unavailable"]


class VectorRecord(BaseModel):
    """A single vector plus its metadata to upsert."""

    id: str
    vector: list[float]
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorMatch(BaseModel):
    """A query result: a vector id, its similarity score and metadata."""

    id: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorStoreHealth(BaseModel):
    """Reachability of the vector database."""

    status: VectorStoreStatus
    provider: str
    detail: str | None = None


class BaseVectorStore(ABC):
    """Interface every vector database adapter must implement."""

    provider: str
    dimension: int

    @abstractmethod
    async def upsert(self, namespace: str, records: list[VectorRecord]) -> int:
        """Upsert ``records`` into ``namespace`` and return the number written."""

    @abstractmethod
    async def query(
        self,
        namespace: str,
        vector: list[float],
        *,
        top_k: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        """Return the ``top_k`` closest records within ``namespace``.

        ``metadata_filter`` is *additional* to the mandatory namespace scope and
        can never widen the search beyond the tenant.
        """

    @abstractmethod
    async def delete(self, namespace: str, ids: list[str]) -> int:
        """Delete vectors by id within ``namespace`` and return the count removed."""

    @abstractmethod
    async def count(self, namespace: str) -> int:
        """Return the number of vectors stored in ``namespace``."""

    @abstractmethod
    async def health_check(self) -> VectorStoreHealth:
        """Perform a real reachability check against the backing store."""
