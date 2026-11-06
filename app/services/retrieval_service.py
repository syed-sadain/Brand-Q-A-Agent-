"""Semantic retrieval service.

Retrieval is always scoped to the tenant namespace derived from the validated
``tenant_id``; there is no API here to run an unrestricted global search.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.core.exceptions import EmptyCorpusError, VectorStoreError
from app.core.logging import get_logger
from app.core.security import tenant_namespace
from app.integrations.embeddings.base import BaseEmbeddings
from app.integrations.vectorstores.base import BaseVectorStore
from app.models.document import RetrievedChunk
from app.repositories.document_repository import DocumentRepository

logger = get_logger(__name__)


class RetrievalService:
    """Embed a question and retrieve the most relevant tenant-scoped chunks."""

    def __init__(
        self,
        *,
        vector_store: BaseVectorStore,
        embeddings: BaseEmbeddings,
        repository: DocumentRepository,
        settings: Settings,
    ) -> None:
        self._vector_store = vector_store
        self._embeddings = embeddings
        self._repository = repository
        self._settings = settings

    async def search(
        self,
        tenant_id: str,
        question: str,
        *,
        top_k: int | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        """Return the top ``k`` chunks for ``question`` within ``tenant_id``.

        Raises:
            EmptyCorpusError: when the tenant has no indexed documents at all.
            VectorStoreError: when the vector database query fails.
        """
        namespace = tenant_namespace(tenant_id)
        document_count = await self._repository.count_documents(tenant_id)
        if document_count == 0:
            raise EmptyCorpusError(f"No documents have been ingested for tenant '{tenant_id}'.")

        try:
            vector = await self._embeddings.aembed_query(question)
            matches = await self._vector_store.query(
                namespace,
                vector,
                top_k=top_k or self._settings.retrieval_top_k,
                metadata_filter=metadata_filter,
            )
        except VectorStoreError:
            raise
        except Exception as exc:
            logger.error("retrieval failed", extra={"tenant_id": tenant_id, "error": str(exc)})
            raise VectorStoreError("The retrieval query failed.") from exc

        chunks = [RetrievedChunk.from_match(match) for match in matches]
        chunks = self._deduplicate(chunks)
        logger.info(
            "retrieval completed",
            extra={"tenant_id": tenant_id, "retrieved": len(chunks), "namespace": namespace},
        )
        return chunks

    @staticmethod
    def _deduplicate(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Remove duplicate chunks, keeping the highest scoring occurrence."""
        best: dict[tuple[str, int], RetrievedChunk] = {}
        order: list[tuple[str, int]] = []
        for chunk in chunks:
            key = (chunk.doc_id, chunk.chunk_index)
            if key not in best:
                best[key] = chunk
                order.append(key)
            elif chunk.score > best[key].score:
                best[key] = chunk
        return [best[key] for key in order]
