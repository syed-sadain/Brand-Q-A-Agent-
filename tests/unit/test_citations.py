"""Unit tests for citation generation."""

from __future__ import annotations

from app.models.document import RetrievedChunk
from app.services.citation_service import CitationService
from app.utils.text_utils import truncate


def _chunk(
    *,
    doc_id: str = "doc-1",
    chunk_index: int = 0,
    source: str = "https://example.com/asana",
    brand: str = "Asana",
    text: str = "Asana is pricier per seat than Trello.",
) -> RetrievedChunk:
    return RetrievedChunk(
        id=f"{doc_id}-{chunk_index}",
        text=text,
        score=0.9,
        tenant_id="acme",
        doc_id=doc_id,
        chunk_index=chunk_index,
        source=source,
        brand=brand,
        content_hash="h" * 64,
    )


def test_citations_are_built_from_the_actual_chunks() -> None:
    service = CitationService()
    citations = service.build([_chunk()])
    assert len(citations) == 1
    assert citations[0].source == "https://example.com/asana"
    assert citations[0].brand == "Asana"
    assert citations[0].chunk_text == "Asana is pricier per seat than Trello."


def test_citations_are_deduplicated_per_source_chunk() -> None:
    service = CitationService()
    chunk = _chunk()
    citations = service.build([chunk, chunk, chunk])
    assert len(citations) == 1


def test_distinct_chunks_produce_distinct_citations() -> None:
    service = CitationService()
    citations = service.build([_chunk(chunk_index=0), _chunk(chunk_index=1)])
    assert len(citations) == 2


def test_long_chunk_text_is_truncated() -> None:
    service = CitationService(max_chunk_chars=40)
    long_text = "word " * 100
    citations = service.build([_chunk(text=long_text)])
    assert citations[0].chunk_text == truncate(long_text, 40)
    assert len(citations[0].chunk_text) <= 41  # 40 chars + ellipsis


def test_no_citations_without_chunks() -> None:
    assert CitationService().build([]) == []


def test_citation_falls_back_to_unknown_labels() -> None:
    service = CitationService()
    citations = service.build([_chunk(source="", brand="")])
    assert citations[0].source == "unknown"
    assert citations[0].brand == "unknown"
