"""ChromaDB vector store adapter (optional local backend).

Each tenant gets its own collection, which provides isolation equivalent to
Pinecone namespaces. Chroma is imported lazily so the dependency stays optional:
installing ``chromadb`` is only required when ``VECTOR_STORE_PROVIDER=chroma``.
"""

from __future__ import annotations

import asyncio
import threading
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


class ChromaVectorStore(BaseVectorStore):
    """Chroma backed store with one collection per tenant."""

    provider = "chroma"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.dimension = settings.embedding_dimension
        self._client: Any | None = None
        self._collections: dict[str, Any] = {}
        # Chroma's client and collection registry are not thread safe, yet the
        # ingestion pipeline runs several documents concurrently through
        # ``asyncio.to_thread``. Guarding client/collection access keeps those
        # concurrent calls from racing on shared Chroma state.
        self._lock = threading.RLock()

    def _get_client(self) -> Any:
        with self._lock:
            if self._client is None:
                try:
                    import chromadb
                except ImportError as exc:  # pragma: no cover - optional dependency
                    raise VectorStoreError(
                        "chromadb is not installed. Install it or use VECTOR_STORE_PROVIDER=memory."
                    ) from exc
                self._client = chromadb.PersistentClient(path=self._settings.chroma_persist_dir)
            return self._client

    def _collection(self, namespace: str) -> Any:
        """Return the cached collection for ``namespace``, creating it once.

        The handle is cached and its creation is lock-guarded because
        ``get_or_create_collection`` mutates shared client state and raises
        ``RuntimeError: Set changed size during iteration`` when two concurrent
        ingestion tasks race on it.
        """
        with self._lock:
            collection = self._collections.get(namespace)
            if collection is None:
                client = self._get_client()
                collection = client.get_or_create_collection(
                    name=namespace, metadata={"hnsw:space": "cosine"}
                )
                self._collections[namespace] = collection
            return collection

    async def _run(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except VectorStoreError:
            raise
        except Exception as exc:
            logger.error("chroma operation failed", extra={"error": str(exc)})
            raise VectorStoreError("The Chroma vector database operation failed.") from exc

    async def upsert(self, namespace: str, records: list[VectorRecord]) -> int:
        if not records:
            return 0
        collection = await self._run(self._collection, namespace)
        await self._run(
            collection.upsert,
            ids=[record.id for record in records],
            embeddings=[record.vector for record in records],
            metadatas=[record.metadata for record in records],
            documents=[str(record.metadata.get("text", "")) for record in records],
        )
        return len(records)

    async def query(
        self,
        namespace: str,
        vector: list[float],
        *,
        top_k: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        collection = await self._run(self._collection, namespace)
        response = await self._run(
            collection.query,
            query_embeddings=[vector],
            n_results=top_k,
            where=metadata_filter or None,
            include=["metadatas", "distances"],
        )
        ids = (response.get("ids") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]
        metadatas = (response.get("metadatas") or [[]])[0]
        results: list[VectorMatch] = []
        for index, vector_id in enumerate(ids):
            distance = distances[index] if index < len(distances) else 1.0
            metadata = metadatas[index] if index < len(metadatas) else {}
            results.append(
                VectorMatch(id=vector_id, score=1.0 - float(distance), metadata=metadata or {})
            )
        return results

    async def delete(self, namespace: str, ids: list[str]) -> int:
        if not ids:
            return 0
        collection = await self._run(self._collection, namespace)
        await self._run(collection.delete, ids=ids)
        return len(ids)

    async def count(self, namespace: str) -> int:
        collection = await self._run(self._collection, namespace)
        return int(await self._run(collection.count))

    async def health_check(self) -> VectorStoreHealth:
        try:
            client = await self._run(self._get_client)
            await self._run(client.heartbeat)
            return VectorStoreHealth(status="healthy", provider=self.provider)
        except VectorStoreError as exc:
            return VectorStoreHealth(
                status="unavailable", provider=self.provider, detail=exc.message
            )
