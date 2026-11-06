"""Document chunking with a token-aware recursive splitter."""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.document import DocumentChunk, LoadedDocument
from app.utils.text_utils import count_tokens

logger = get_logger(__name__)

_SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]


def build_splitter(settings: Settings) -> RecursiveCharacterTextSplitter:
    """Create the configured token-aware recursive splitter.

    ``RecursiveCharacterTextSplitter`` is used with a token counting length
    function so ``CHUNK_SIZE``/``CHUNK_OVERLAP`` are expressed in tokens
    (~400/50 by default), matching the specification.
    """
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        length_function=count_tokens,
        separators=_SEPARATORS,
        keep_separator=True,
    )


def chunk_document(document: LoadedDocument, settings: Settings) -> list[DocumentChunk]:
    """Split ``document`` into metadata-carrying chunks.

    Vector ids use the ``{doc_id}-{chunk_index}`` convention so that re-ingesting
    a document overwrites its existing vectors instead of duplicating them.
    """
    splitter = build_splitter(settings)
    pieces = splitter.split_text(document.text)
    chunks: list[DocumentChunk] = []
    for piece in pieces:
        content = piece.strip()
        if not content:
            continue
        chunk_index = len(chunks)
        chunks.append(
            DocumentChunk(
                tenant_id=document.tenant_id,
                doc_id=document.doc_id,
                chunk_index=chunk_index,
                source=document.source,
                brand=document.brand,
                content_hash=document.content_hash,
                text=content,
                vector_id=f"{document.doc_id}-{chunk_index}",
            )
        )
    logger.info(
        "document chunked",
        extra={
            "doc_id": document.doc_id,
            "tenant_id": document.tenant_id,
            "chunks": len(chunks),
            "tokens": count_tokens(document.text),
        },
    )
    return chunks
