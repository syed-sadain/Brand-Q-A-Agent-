"""Internal domain models for documents and chunks."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class LoadedDocument:
    """A normalised document ready for chunking and embedding."""

    tenant_id: str
    doc_id: str
    brand: str
    source: str
    text: str
    content_hash: str
    is_url_source: bool = False


@dataclass(slots=True)
class DocumentChunk:
    """A single chunk of a document with the metadata required by the spec."""

    tenant_id: str
    doc_id: str
    chunk_index: int
    source: str
    brand: str
    content_hash: str
    text: str
    vector_id: str = ""

    def metadata(self) -> dict[str, str | int]:
        """Return the metadata persisted alongside the vector."""
        return {
            "tenant_id": self.tenant_id,
            "doc_id": self.doc_id,
            "chunk_index": self.chunk_index,
            "source": self.source,
            "brand": self.brand,
            "content_hash": self.content_hash,
        }


@dataclass(slots=True)
class RetrievedChunk:
    """A chunk returned by a semantic search, with its similarity score."""

    id: str
    text: str
    score: float
    tenant_id: str
    doc_id: str
    chunk_index: int
    source: str
    brand: str
    content_hash: str

    @classmethod
    def from_match(cls, match: object) -> RetrievedChunk:
        """Build a :class:`RetrievedChunk` from a vector store match."""
        metadata: dict = getattr(match, "metadata", {}) or {}
        return cls(
            id=str(getattr(match, "id", "")),
            text=str(metadata.get("text", "")),
            score=float(getattr(match, "score", 0.0)),
            tenant_id=str(metadata.get("tenant_id", "")),
            doc_id=str(metadata.get("doc_id", "")),
            chunk_index=int(metadata.get("chunk_index", 0)),
            source=str(metadata.get("source", "")),
            brand=str(metadata.get("brand", "")),
            content_hash=str(metadata.get("content_hash", "")),
        )


@dataclass(slots=True)
class IngestionResult:
    """Aggregate outcome of an ingestion run."""

    documents_stored: int = 0
    chunks_stored: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)
