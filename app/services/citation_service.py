"""Citation construction from retrieved evidence."""

from __future__ import annotations

from app.models.document import RetrievedChunk
from app.schemas.citation import Citation
from app.utils.text_utils import truncate

NOT_FOUND_ANSWER = "The requested information is not available in the provided documents."


class CitationService:
    """Build citations strictly from the evidence used for the answer."""

    def __init__(self, *, max_chunk_chars: int = 500) -> None:
        self._max_chunk_chars = max_chunk_chars

    def build(self, chunks: list[RetrievedChunk]) -> list[Citation]:
        """Return one citation per distinct source chunk.

        Sources are never fabricated: every citation is derived from metadata of
        a chunk that was actually retrieved and used.
        """
        citations: list[Citation] = []
        seen: set[tuple[str, str, int]] = set()
        for chunk in chunks:
            key = (chunk.source, chunk.doc_id, chunk.chunk_index)
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                Citation(
                    source=chunk.source or "unknown",
                    brand=chunk.brand or "unknown",
                    chunk_text=truncate(chunk.text, self._max_chunk_chars),
                )
            )
        return citations
