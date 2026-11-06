"""Pinecone vector store adapter (primary production backend).

Tenant isolation is enforced with **one namespace per tenant** derived from the
validated ``tenant_id``; every upsert, query and delete is namespace scoped.
The synchronous Pinecone SDK is executed in a worker thread so the public
interface stays fully asynchronous.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import Settings
from app.core.exceptions import VectorStoreError
from app.core.logging import get_logger
from app.integrations.vectorstores.base import (
    BaseVectorStore,
    VectorMatch,
    VectorRecord,
    VectorStoreHealth,
)

logger = get_logger(__name__)

_PINECONE_UPSERT_BATCH = 100


class PineconeVectorStore(BaseVectorStore):
    """Pinecone backed vector store with mandatory tenant namespaces."""

    provider = "pinecone"

    def __init__(self, settings: Settings) -> None:
        if not settings.pinecone_api_key:
            raise VectorStoreError(
                "PINECONE_API_KEY is required when VECTOR_STORE_PROVIDER=pinecone."
            )
        self._settings = settings
        self.dimension = settings.embedding_dimension
        self._index_name = settings.pinecone_index_name
        self._client: Any | None = None
        self._index: Any | None = None

    # ------------------------------------------------------------------ internals
    def _get_client(self) -> Any:
        if self._client is None:
            from pinecone import Pinecone

            self._client = Pinecone(api_key=self._settings.pinecone_api_key)
        return self._client

    def _get_index_sync(self) -> Any:
        client = self._get_client()
        if not client.has_index(self._index_name):
            from pinecone import ServerlessSpec

            logger.info("creating pinecone index", extra={"index": self._index_name})
            client.create_index(
                name=self._index_name,
                dimension=self.dimension,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud=self._settings.pinecone_cloud,
                    region=self._settings.pinecone_region,
                ),
            )
        return client.Index(self._index_name)

    def _get_index(self) -> Any:
        if self._index is None:
            self._index = self._get_index_sync()
        return self._index

    async def _run(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except VectorStoreError:
            raise
        except Exception as exc:
            logger.error("pinecone operation failed", extra={"error": str(exc)})
            raise VectorStoreError("The Pinecone vector database operation failed.") from exc

    # ------------------------------------------------------------------ api
    async def upsert(self, namespace: str, records: list[VectorRecord]) -> int:
        if not records:
            return 0
        index = await self._run(self._get_index)
        written = 0
        for start in range(0, len(records), _PINECONE_UPSERT_BATCH):
            batch = records[start : start + _PINECONE_UPSERT_BATCH]
            payload = [
                {"id": record.id, "values": record.vector, "metadata": record.metadata}
                for record in batch
            ]
            await self._run(index.upsert, vectors=payload, namespace=namespace)
            written += len(batch)
        return written

    async def query(
        self,
        namespace: str,
        vector: list[float],
        *,
        top_k: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        index = await self._run(self._get_index)
        pinecone_filter = (
            {key: {"$eq": value} for key, value in metadata_filter.items()}
            if metadata_filter
            else None
        )
        response = await self._run(
            index.query,
            vector=vector,
            top_k=top_k,
            namespace=namespace,
            include_metadata=True,
            filter=pinecone_filter,
        )
        matches = getattr(response, "matches", None) or response.get("matches", [])
        results: list[VectorMatch] = []
        for match in matches:
            match_id = getattr(match, "id", None) or match.get("id")
            score = getattr(match, "score", None)
            if score is None:
                score = match.get("score", 0.0)
            metadata = getattr(match, "metadata", None) or match.get("metadata", {}) or {}
            results.append(VectorMatch(id=match_id, score=float(score), metadata=dict(metadata)))
        return results

    async def delete(self, namespace: str, ids: list[str]) -> int:
        if not ids:
            return 0
        index = await self._run(self._get_index)
        await self._run(index.delete, ids=ids, namespace=namespace)
        return len(ids)

    async def count(self, namespace: str) -> int:
        index = await self._run(self._get_index)
        stats = await self._run(index.describe_index_stats)
        namespaces = getattr(stats, "namespaces", None)
        if namespaces is None and isinstance(stats, dict):
            namespaces = stats.get("namespaces", {})
        entry = (namespaces or {}).get(namespace)
        if entry is None:
            return 0
        if isinstance(entry, dict):
            return int(entry.get("vector_count", 0))
        return int(getattr(entry, "vector_count", 0))

    async def health_check(self) -> VectorStoreHealth:
        try:
            client = await self._run(self._get_client)
            exists = await self._run(client.has_index, self._index_name)
            if not exists:
                return VectorStoreHealth(
                    status="degraded",
                    provider=self.provider,
                    detail=f"index '{self._index_name}' does not exist yet",
                )
            index = await self._run(self._get_index)
            await self._run(index.describe_index_stats)
            return VectorStoreHealth(status="healthy", provider=self.provider)
        except VectorStoreError as exc:
            return VectorStoreHealth(
                status="unavailable", provider=self.provider, detail=exc.message
            )
