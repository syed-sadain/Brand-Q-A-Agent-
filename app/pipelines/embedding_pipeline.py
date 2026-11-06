"""Embedding pipeline: turn chunks into vector records ready for upsert."""

from __future__ import annotations

from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger
from app.integrations.embeddings.base import BaseEmbeddings
from app.integrations.vectorstores.base import VectorRecord
from app.models.document import DocumentChunk

logger = get_logger(__name__)


def _validate_dimensions(embeddings: BaseEmbeddings, vectors: list[list[float]]) -> None:
    for vector in vectors:
        if len(vector) != embeddings.dimension:
            raise ConfigurationError(
                f"Embedding dimension mismatch: model '{embeddings.model}' produced "
                f"{len(vector)} values but EMBEDDING_DIMENSION is {embeddings.dimension}. "
                "The vector index dimension must match the embedding model."
            )


async def embed_chunks(
    chunks: list[DocumentChunk], embeddings: BaseEmbeddings
) -> list[VectorRecord]:
    """Embed ``chunks`` and return upsert-ready :class:`VectorRecord` objects.

    The chunk text is stored in metadata so that retrieved evidence can be cited
    without a second round-trip to the source.
    """
    if not chunks:
        return []
    vectors = await embeddings.aembed_documents([chunk.text for chunk in chunks])
    _validate_dimensions(embeddings, vectors)
    records: list[VectorRecord] = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        metadata = chunk.metadata()
        metadata["text"] = chunk.text
        records.append(VectorRecord(id=chunk.vector_id, vector=vector, metadata=metadata))
    logger.info("chunks embedded", extra={"count": len(records), "model": embeddings.model})
    return records
