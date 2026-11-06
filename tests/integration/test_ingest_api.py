"""Integration tests for ``POST /tenants/{tenant_id}/ingest``.

These exercise the real FastAPI application (routing, request validation,
exception handlers, response models) with the shared offline fakes injected via
``dependency_overrides`` — no network and no LLM API key are required.
"""

from __future__ import annotations

import httpx
import respx

from app.core.security import tenant_namespace
from tests.conftest import ASANA_DOC, TRELLO_DOC, FakeLLM

_HTML = (
    "<html><head><title>PM tools compared</title></head><body><main><p>"
    "Asana and Trello are compared across pricing and features for small teams in this "
    "article about project management software choices and per-seat pricing."
    "</p></main></body></html>"
)


def test_ingest_raw_text_returns_counts(client) -> None:
    response = client.post(
        "/tenants/acme/ingest",
        json={
            "documents": [{"text": ASANA_DOC, "source": "synthetic://asana-1", "brand": "Asana"}]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["documents_stored"] == 1
    assert body["chunks_stored"] >= 1
    assert body["errors"] == []


def test_ingest_multiple_documents_returns_aggregate_counts(client) -> None:
    response = client.post(
        "/tenants/acme/ingest",
        json={
            "documents": [
                {"text": ASANA_DOC, "source": "synthetic://asana-1", "brand": "Asana"},
                {"text": TRELLO_DOC, "source": "synthetic://trello-1", "brand": "Trello"},
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["documents_stored"] == 2


async def test_reingesting_the_same_document_does_not_grow_counts(client, vector_store) -> None:
    payload = {
        "documents": [{"text": ASANA_DOC, "source": "synthetic://asana-1", "brand": "Asana"}]
    }

    first = client.post("/tenants/acme/ingest", json=payload).json()
    count_after_first = await vector_store.count(tenant_namespace("acme"))
    second = client.post("/tenants/acme/ingest", json=payload).json()

    assert first["chunks_stored"] == second["chunks_stored"]
    assert first["documents_stored"] == second["documents_stored"] == 1
    assert await vector_store.count(tenant_namespace("acme")) == count_after_first


@respx.mock
def test_ingest_url_document_is_fetched_and_indexed(make_client, allow_all_urls) -> None:
    url = "https://example.com/pm-tools"
    respx.get(url).mock(
        return_value=httpx.Response(200, html=_HTML, headers={"content-type": "text/html"})
    )
    local_client = make_client(FakeLLM())

    response = local_client.post(
        "/tenants/acme/ingest", json={"documents": [{"url": url, "brand": "Asana"}]}
    )

    assert response.status_code == 200
    assert response.json()["documents_stored"] == 1


def test_ingest_partial_failure_returns_errors_without_aborting(client) -> None:
    response = client.post(
        "/tenants/acme/ingest",
        json={
            "documents": [
                {"text": ASANA_DOC, "source": "synthetic://asana-1", "brand": "Asana"},
                {"text": "hi", "source": "synthetic://too-short", "brand": "Trello"},
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["documents_stored"] == 1
    assert len(body["errors"]) == 1
    assert body["errors"][0]["code"] == "empty_document"
    assert body["errors"][0]["source"] == "synthetic://too-short"


def test_ingest_rejects_invalid_tenant_id(client) -> None:
    response = client.post(
        "/tenants/-invalid-/ingest",
        json={"documents": [{"text": ASANA_DOC, "brand": "Asana", "source": "s"}]},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_tenant_id"


def test_ingest_rejects_document_with_both_url_and_text(client) -> None:
    response = client.post(
        "/tenants/acme/ingest",
        json={"documents": [{"url": "https://example.com/a", "text": ASANA_DOC, "brand": "Asana"}]},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_error"


def test_ingest_rejects_document_without_any_source(client) -> None:
    response = client.post("/tenants/acme/ingest", json={"documents": [{"brand": "Asana"}]})

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_error"


def test_ingest_rejects_empty_document_list(client) -> None:
    response = client.post("/tenants/acme/ingest", json={"documents": []})

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_error"


async def test_ingest_documents_land_in_the_tenant_namespace(client, vector_store) -> None:
    client.post(
        "/tenants/acme/ingest",
        json={
            "documents": [{"text": ASANA_DOC, "source": "synthetic://asana-1", "brand": "Asana"}]
        },
    )

    assert await vector_store.count(tenant_namespace("acme")) > 0
    assert await vector_store.count(tenant_namespace("globex")) == 0
