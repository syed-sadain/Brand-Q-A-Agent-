"""In-memory vector store.

A real, dependency-free implementation used for local development and for the
automated test-suite. It is **not** presented as Pinecone: it is a distinct,
clearly labelled backend selected with ``VECTOR_STORE_PROVIDER=memory``.
"""

from __future__ import annotations

import math
from typing import Any

from app.core.exceptions import VectorStoreError
from app.integrations.vectorstores.base import (
    BaseVectorStore,
    VectorMatch,
    VectorRecord,
    VectorStoreHealth,
)


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise VectorStoreError("Vector dimension mismatch between store and query.")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _matches_filter(metadata: dict[str, Any], metadata_filter: dict[str, Any] | None) -> bool:
    if not metadata_filter:
        return True
    return all(metadata.get(key) == value for key, value in metadata_filter.items())


class InMemoryVectorStore(BaseVectorStore):
    """Namespace-isolated in-memory vector index."""

    provider = "memory"

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self._namespaces: dict[str, dict[str, VectorRecord]] = {}

    async def upsert(self, namespace: str, records: list[VectorRecord]) -> int:
        store = self._namespaces.setdefault(namespace, {})
        for record in records:
            store[record.id] = record
        return len(records)

    async def query(
        self,
        namespace: str,
        vector: list[float],
        *,
        top_k: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        store = self._namespaces.get(namespace, {})
        scored: list[VectorMatch] = []
        for record in store.values():
            if not _matches_filter(record.metadata, metadata_filter):
                continue
            scored.append(
                VectorMatch(
                    id=record.id, score=_cosine(vector, record.vector), metadata=record.metadata
                )
            )
        scored.sort(key=lambda match: match.score, reverse=True)
        return scored[:top_k]

    async def delete(self, namespace: str, ids: list[str]) -> int:
        store = self._namespaces.get(namespace)
        if not store:
            return 0
        removed = 0
        for vector_id in ids:
            if store.pop(vector_id, None) is not None:
                removed += 1
        return removed

    async def count(self, namespace: str) -> int:
        return len(self._namespaces.get(namespace, {}))

    async def health_check(self) -> VectorStoreHealth:
        return VectorStoreHealth(status="healthy", provider=self.provider, detail="in-memory store")
