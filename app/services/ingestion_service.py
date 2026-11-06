"""Ingestion service: the business logic behind ``POST /tenants/{tenant_id}/ingest``.

Responsibilities:
* load each document (URL fetch or raw text),
* chunk it with token-aware splitting,
* embed the chunks,
* upsert tenant-scoped vectors using ``{doc_id}-{chunk_index}`` ids,
* remove vectors that became obsolete when a document's chunk count shrinks,
* update the document registry so re-ingestion stays idempotent.
"""

from __future__ import annotations

import asyncio

from app.core.config import Settings
from app.core.exceptions import AppError, EmptyDocumentError
from app.core.logging import get_logger
from app.core.security import tenant_namespace
from app.integrations.embeddings.base import BaseEmbeddings
from app.integrations.vectorstores.base import BaseVectorStore
from app.models.document import IngestionResult
from app.pipelines.document_chunker import chunk_document
from app.pipelines.document_loader import DocumentLoader
from app.pipelines.embedding_pipeline import embed_chunks
from app.repositories.document_repository import DocumentRecord, DocumentRepository
from app.schemas.ingest import IngestDocumentRequest

logger = get_logger(__name__)

_MAX_CONCURRENT_FETCHES = 4


class IngestionService:
    """Load, chunk, embed and store documents for a tenant."""

    def __init__(
        self,
        *,
        settings: Settings,
        embeddings: BaseEmbeddings,
        vector_store: BaseVectorStore,
        repository: DocumentRepository,
    ) -> None:
        self._settings = settings
        self._embeddings = embeddings
        self._vector_store = vector_store
        self._repository = repository

    async def ingest(
        self, tenant_id: str, documents: list[IngestDocumentRequest]
    ) -> IngestionResult:
        """Ingest ``documents`` for ``tenant_id``.

        Documents are processed concurrently (bounded). A failure for one document
        is recorded and does not abort the whole batch, which keeps ingestion safe
        for retries and partial failures. If *every* document fails, the first
        error is raised so the API can return a meaningful status code.
        """
        namespace = tenant_namespace(tenant_id)
        result = IngestionResult()
        first_error: AppError | None = None
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)

        async with DocumentLoader(self._settings) as loader:

            async def _process(document: IngestDocumentRequest) -> None:
                nonlocal first_error
                async with semaphore:
                    source_label = (
                        str(document.url) if document.url else (document.source or "raw-text")
                    )
                    try:
                        loaded = await loader.load(
                            tenant_id,
                            url=str(document.url) if document.url else None,
                            text=document.text,
                            source=document.source,
                            brand=document.brand,
                        )
                        chunks = chunk_document(loaded, self._settings)
                        if not chunks:
                            raise EmptyDocumentError(
                                f"The document from '{source_label}' produced no chunks."
                            )
                        records = await embed_chunks(chunks, self._embeddings)
                        await self._remove_obsolete_chunks(
                            namespace, tenant_id, loaded.doc_id, len(chunks)
                        )
                        await self._vector_store.upsert(namespace, records)
                        await self._repository.upsert(
                            DocumentRecord(
                                tenant_id=tenant_id,
                                doc_id=loaded.doc_id,
                                source=loaded.source,
                                brand=loaded.brand,
                                content_hash=loaded.content_hash,
                                chunk_count=len(chunks),
                            )
                        )
                        result.documents_stored += 1
                        result.chunks_stored += len(chunks)
                    except AppError as exc:
                        logger.warning(
                            "document ingestion failed",
                            extra={"source": source_label, "code": exc.code},
                        )
                        result.errors.append(
                            {"source": source_label, "code": exc.code, "message": exc.message}
                        )
                        if first_error is None:
                            first_error = exc
                    except Exception:
                        logger.exception(
                            "unexpected ingestion failure", extra={"source": source_label}
                        )
                        result.errors.append(
                            {
                                "source": source_label,
                                "code": "ingestion_failed",
                                "message": "The document could not be ingested.",
                            }
                        )

            await asyncio.gather(*(_process(document) for document in documents))

        if result.documents_stored == 0 and first_error is not None:
            raise first_error

        logger.info(
            "ingestion completed",
            extra={
                "tenant_id": tenant_id,
                "documents_stored": result.documents_stored,
                "chunks_stored": result.chunks_stored,
                "errors": len(result.errors),
            },
        )
        return result

    async def _remove_obsolete_chunks(
        self, namespace: str, tenant_id: str, doc_id: str, new_chunk_count: int
    ) -> None:
        """Delete vectors left over from a previous ingestion with more chunks."""
        previous = await self._repository.get(tenant_id, doc_id)
        if previous is None or previous.chunk_count <= new_chunk_count:
            return
        obsolete_ids = [
            f"{doc_id}-{index}" for index in range(new_chunk_count, previous.chunk_count)
        ]
        removed = await self._vector_store.delete(namespace, obsolete_ids)
        logger.info(
            "removed obsolete chunks",
            extra={"doc_id": doc_id, "removed": removed, "previous": previous.chunk_count},
        )
