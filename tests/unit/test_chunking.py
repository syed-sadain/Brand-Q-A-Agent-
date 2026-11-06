"""Unit tests for token-aware document chunking."""

from __future__ import annotations

from app.core.config import Settings
from app.models.document import LoadedDocument
from app.pipelines.document_chunker import build_splitter, chunk_document
from app.utils.text_utils import count_tokens


def _loaded(text: str, *, doc_id: str = "doc-abc", tenant_id: str = "acme") -> LoadedDocument:
    return LoadedDocument(
        tenant_id=tenant_id,
        doc_id=doc_id,
        brand="Asana",
        source="https://example.com/article",
        text=text,
        content_hash="c" * 64,
    )


def test_splitter_honours_configured_token_limits() -> None:
    settings = Settings(
        embedding_provider="hashing",
        embedding_dimension=64,
        chunk_size=400,
        chunk_overlap=50,
    )
    splitter = build_splitter(settings)
    assert splitter._chunk_size == 400
    assert splitter._chunk_overlap == 50


def test_long_document_is_split_into_multiple_chunks(settings: Settings) -> None:
    text = "Asana and Trello pricing comparison. " * 60
    chunks = chunk_document(_loaded(text), settings)
    assert len(chunks) > 1


def test_short_document_produces_a_single_chunk(settings: Settings) -> None:
    chunks = chunk_document(_loaded("Asana is priced higher than Trello."), settings)
    assert len(chunks) == 1


def test_every_chunk_carries_the_required_metadata(settings: Settings) -> None:
    chunks = chunk_document(_loaded("Some project management comparison text."), settings)
    metadata = chunks[0].metadata()
    assert metadata == {
        "tenant_id": "acme",
        "doc_id": "doc-abc",
        "chunk_index": 0,
        "source": "https://example.com/article",
        "brand": "Asana",
        "content_hash": "c" * 64,
    }


def test_vector_ids_follow_the_doc_id_chunk_index_convention(settings: Settings) -> None:
    chunks = chunk_document(_loaded("word " * 200), settings)
    assert [chunk.vector_id for chunk in chunks] == [
        f"doc-abc-{index}" for index in range(len(chunks))
    ]


def test_chunk_indices_are_sequential(settings: Settings) -> None:
    chunks = chunk_document(_loaded("word " * 200), settings)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_chunks_respect_the_configured_token_size(settings: Settings) -> None:
    chunks = chunk_document(_loaded("word " * 300), settings)
    # With chunk_size=40 the splitter should not (materially) exceed the limit.
    assert all(
        count_tokens(chunk.text) <= settings.chunk_size + settings.chunk_overlap for chunk in chunks
    )


def test_empty_document_produces_no_chunks(settings: Settings) -> None:
    assert chunk_document(_loaded(""), settings) == []


def test_whitespace_only_document_produces_no_chunks(settings: Settings) -> None:
    assert chunk_document(_loaded("   \n\n   "), settings) == []


def test_overlapping_chunks_share_content(settings: Settings) -> None:
    text = " ".join(f"token{index}" for index in range(200))
    chunks = chunk_document(_loaded(text), settings)
    assert len(chunks) > 2
    # Overlap means consecutive chunks are not entirely disjoint.
    overlap_exists = any(
        set(chunks[i].text.split()) & set(chunks[i + 1].text.split())
        for i in range(len(chunks) - 1)
    )
    assert overlap_exists
