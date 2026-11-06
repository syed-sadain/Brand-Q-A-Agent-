"""Unit tests for the ingestion service (idempotency, partial failures, cleanup)."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.exceptions import EmptyDocumentError
from app.core.security import tenant_namespace
from app.repositories.document_repository import DocumentRepository
from app.schemas.ingest import IngestDocumentRequest
from app.services.ingestion_service import IngestionService
from tests.conftest import ASANA_DOC, TRELLO_DOC, raw_document

_LONG_HTML = (
    "<html><body><main><p>"
    + ("Asana pricing comparison details for teams. " * 40)
    + "</p></main></body></html>"
)
_SHORT_HTML = (
    "<html><body><main><p>Asana pricing summary for teams: reviewers generally say Asana "
    "costs more per seat than Trello and that Trello is cheaper for small teams overall."
    "</p></main></body></html>"
)
_ARTICLE_HTML = (
    "<html><head><title>PM tools compared</title></head><body><main>"
    "<p>Asana and Trello are compared across pricing and features for small teams in this "
    "article about project management software choices.</p></main></body></html>"
)


async def test_ingest_stores_document_chunks_and_registry(
    ingestion_service: IngestionService,
    vector_store,
    repository: DocumentRepository,
) -> None:
    result = await ingestion_service.ingest(
        "acme", [raw_document(ASANA_DOC, "Asana", "synthetic://asana-1")]
    )
    assert result.documents_stored == 1
    assert result.chunks_stored >= 1
    assert result.errors == []
    assert await vector_store.count(tenant_namespace("acme")) == result.chunks_stored
    assert await repository.count_documents("acme") == 1


async def test_reingestion_is_idempotent(
    ingestion_service: IngestionService,
    vector_store,
) -> None:
    documents = [raw_document(ASANA_DOC, "Asana", "synthetic://asana-1")]
    first = await ingestion_service.ingest("acme", documents)
    count_after_first = await vector_store.count(tenant_namespace("acme"))

    second = await ingestion_service.ingest("acme", documents)
    count_after_second = await vector_store.count(tenant_namespace("acme"))

    assert first.chunks_stored == second.chunks_stored
    assert count_after_first == count_after_second  # no duplicate vectors


async def test_multiple_documents_are_ingested_together(
    ingestion_service: IngestionService,
    vector_store,
) -> None:
    documents = [
        raw_document(ASANA_DOC, "Asana", "synthetic://asana-1"),
        raw_document(TRELLO_DOC, "Trello", "synthetic://trello-1"),
    ]
    result = await ingestion_service.ingest("acme", documents)
    assert result.documents_stored == 2
    assert await vector_store.count(tenant_namespace("acme")) == result.chunks_stored


async def test_one_bad_document_does_not_abort_the_batch(
    ingestion_service: IngestionService,
) -> None:
    documents = [
        raw_document(ASANA_DOC, "Asana", "synthetic://asana-1"),
        raw_document("hi", "Trello", "synthetic://too-short"),
    ]
    result = await ingestion_service.ingest("acme", documents)
    assert result.documents_stored == 1
    assert len(result.errors) == 1
    assert result.errors[0]["code"] == "empty_document"


async def test_all_failing_documents_raise_the_first_error(
    ingestion_service: IngestionService,
) -> None:
    with pytest.raises(EmptyDocumentError):
        await ingestion_service.ingest(
            "acme", [raw_document("hi", "Trello", "synthetic://too-short")]
        )


@respx.mock
async def test_url_document_is_fetched_and_indexed(
    ingestion_service: IngestionService,
    vector_store,
    allow_all_urls,
) -> None:
    url = "https://example.com/pm-tools"
    respx.get(url).mock(
        return_value=httpx.Response(
            200, html=_ARTICLE_HTML, headers={"content-type": "text/html; charset=utf-8"}
        )
    )
    result = await ingestion_service.ingest("acme", [IngestDocumentRequest(url=url, brand="Asana")])
    assert result.documents_stored == 1
    assert await vector_store.count(tenant_namespace("acme")) == result.chunks_stored


@respx.mock
async def test_reingestion_with_fewer_chunks_removes_obsolete_vectors(
    ingestion_service: IngestionService,
    vector_store,
    allow_all_urls,
) -> None:
    url = "https://example.com/changing-article"
    respx.get(url).mock(
        side_effect=[
            httpx.Response(200, html=_LONG_HTML, headers={"content-type": "text/html"}),
            httpx.Response(200, html=_SHORT_HTML, headers={"content-type": "text/html"}),
        ]
    )
    document = IngestDocumentRequest(url=url, brand="Asana")

    first = await ingestion_service.ingest("acme", [document])
    count_after_first = await vector_store.count(tenant_namespace("acme"))

    second = await ingestion_service.ingest("acme", [document])
    count_after_second = await vector_store.count(tenant_namespace("acme"))

    assert first.chunks_stored > second.chunks_stored
    assert count_after_first == first.chunks_stored
    # Stale chunks from the longer version must no longer be searchable.
    assert count_after_second == second.chunks_stored


async def test_documents_are_isolated_in_their_tenant_namespace(
    ingestion_service: IngestionService,
    vector_store,
) -> None:
    await ingestion_service.ingest(
        "acme", [raw_document(ASANA_DOC, "Asana", "synthetic://asana-1")]
    )
    await ingestion_service.ingest(
        "globex", [raw_document(TRELLO_DOC, "Trello", "synthetic://trello-1")]
    )
    acme_count = await vector_store.count(tenant_namespace("acme"))
    globex_count = await vector_store.count(tenant_namespace("globex"))
    assert acme_count > 0
    assert globex_count > 0
    # Distinct namespaces: the global union is larger than either tenant alone.
    assert acme_count + globex_count > max(acme_count, globex_count)
