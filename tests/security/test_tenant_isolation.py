"""MANDATORY TEST 1 — strict tenant isolation.

Scenario required by the assignment:

1. Ingest documents under ``tenant_id="acme"``.
2. Ask the same question under ``tenant_id="globex"``.
3. Confirm ``globex`` cannot retrieve ``acme``'s documents.
4. Confirm ``globex`` returns ``found_in_corpus=false`` when it has no matching data.

Isolation is enforced in the vector-store layer (namespace per tenant), not in a
route handler, so it holds no matter which entry point is used.
"""

from __future__ import annotations

import pytest

from app.core.exceptions import EmptyCorpusError
from app.integrations.embeddings.base import BaseEmbeddings
from app.integrations.vectorstores.base import BaseVectorStore, VectorRecord
from app.services.retrieval_service import RetrievalService
from tests.conftest import ASANA_DOC, NOTION_DOC, FakeLLM, ingest, raw_document

QUESTION = "What do reviewers say about Asana's pricing compared to Trello?"


def _retrieval(vector_store, embeddings, repository, settings) -> RetrievalService:
    return RetrievalService(
        vector_store=vector_store, embeddings=embeddings, repository=repository, settings=settings
    )


async def test_mandatory_tenant_isolation_acme_vs_globex(
    ingestion_service,
    make_agent,
    vector_store: BaseVectorStore,
    embeddings: BaseEmbeddings,
    repository,
    settings,
) -> None:
    # 1. Ingest under tenant "acme".
    await ingest(
        ingestion_service,
        "acme",
        [raw_document(ASANA_DOC, "Asana", "synthetic://acme-asana-1")],
    )
    agent = make_agent(FakeLLM(relevance=lambda _prompt: True))

    # acme can answer from its own corpus.
    acme_response = await agent.ask("acme", QUESTION)
    assert acme_response.found_in_corpus is True
    assert acme_response.citations

    # 3. globex cannot retrieve acme's documents: its namespace is empty.
    assert await vector_store.count("tenant-globex") == 0
    assert await vector_store.count("tenant-acme") > 0

    retrieval = _retrieval(vector_store, embeddings, repository, settings)
    with pytest.raises(EmptyCorpusError):
        await retrieval.search("globex", QUESTION)

    # 4. globex returns an honest not-found response.
    globex_response = await agent.ask("globex", QUESTION)
    assert globex_response.found_in_corpus is False
    assert globex_response.citations == []
    assert "not available" in globex_response.answer.lower()


async def test_globex_never_receives_acme_content_when_both_tenants_have_data(
    ingestion_service,
    make_agent,
) -> None:
    """Even with data in both tenants, a query can only see its own tenant's chunks."""
    await ingest(
        ingestion_service,
        "acme",
        [raw_document(ASANA_DOC, "Asana", "synthetic://acme-asana-1")],
    )
    await ingest(
        ingestion_service,
        "globex",
        [raw_document(NOTION_DOC, "Notion", "synthetic://globex-notion-1")],
    )
    agent = make_agent(FakeLLM(relevance=lambda _prompt: True))

    response = await agent.ask("globex", QUESTION)

    sources = {citation.source for citation in response.citations}
    assert "synthetic://acme-asana-1" not in sources
    assert sources <= {"synthetic://globex-notion-1"}


async def test_vector_store_queries_are_scoped_to_the_requested_namespace(
    vector_store: BaseVectorStore,
    embeddings: BaseEmbeddings,
) -> None:
    vector = await embeddings.aembed_query("asana pricing comparison")
    record = VectorRecord(
        id="doc-1-0",
        vector=vector,
        metadata={
            "tenant_id": "acme",
            "doc_id": "doc-1",
            "chunk_index": 0,
            "source": "synthetic://acme-asana-1",
            "brand": "Asana",
            "content_hash": "h" * 64,
            "text": "asana pricing comparison",
        },
    )
    await vector_store.upsert("tenant-acme", [record])

    acme_matches = await vector_store.query("tenant-acme", vector, top_k=5)
    globex_matches = await vector_store.query("tenant-globex", vector, top_k=5)

    assert len(acme_matches) == 1
    # An identical query in another namespace must return nothing.
    assert globex_matches == []


async def test_user_supplied_metadata_filter_cannot_widen_tenant_scope(
    ingestion_service,
    vector_store: BaseVectorStore,
    embeddings: BaseEmbeddings,
    repository,
    settings,
) -> None:
    """A metadata filter is *additional* to the namespace and can never escape it."""
    await ingest(
        ingestion_service,
        "acme",
        [raw_document(ASANA_DOC, "Asana", "synthetic://acme-asana-1")],
    )
    retrieval = _retrieval(vector_store, embeddings, repository, settings)

    # Filtering by acme's own tenant_id while scoped to globex still yields nothing.
    with pytest.raises(EmptyCorpusError):
        await retrieval.search("globex", QUESTION, metadata_filter={"tenant_id": "acme"})


async def test_ask_api_isolates_tenants_end_to_end(make_client) -> None:
    from tests.conftest import ASANA_DOC as _doc

    client = make_client(FakeLLM(relevance=lambda _prompt: True))
    client.post(
        "/tenants/acme/ingest",
        json={
            "documents": [{"text": _doc, "source": "synthetic://acme-asana-1", "brand": "Asana"}]
        },
    )

    acme = client.post("/tenants/acme/ask", json={"question": QUESTION}).json()
    globex = client.post("/tenants/globex/ask", json={"question": QUESTION}).json()

    assert acme["found_in_corpus"] is True
    assert globex["found_in_corpus"] is False
    assert globex["citations"] == []
