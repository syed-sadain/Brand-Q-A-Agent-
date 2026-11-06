"""Integration tests for ``POST /tenants/{tenant_id}/ask``.

The real FastAPI app is driven end-to-end through ``TestClient`` with the offline
:class:`FakeLLM` injected, so every assertion reflects the actual question-answering
workflow, response schema and error mapping.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.core.exceptions import LLMTimeoutError
from app.integrations.llm.base import BaseLLM, LLMHealth, LLMMessage
from app.services.citation_service import NOT_FOUND_ANSWER
from tests.conftest import ASANA_DOC, DEFAULT_ANSWER, FakeLLM

QUESTION = "What do reviewers say about Asana's pricing compared to Trello?"
OFF_TOPIC = "What is the capital of France?"
_INGEST_PAYLOAD = {
    "documents": [{"text": ASANA_DOC, "source": "synthetic://asana-1", "brand": "Asana"}]
}


class _TimeoutLLM(BaseLLM):
    """Grading always times out, exercising the 504 error mapping."""

    provider = "fake"
    model = "fake"

    async def ainvoke(self, messages: list[LLMMessage]) -> str:
        return "unused"

    async def ainvoke_structured(self, messages: list[LLMMessage], schema: type[BaseModel]):
        raise LLMTimeoutError("simulated provider timeout")

    async def health_check(self) -> LLMHealth:
        return LLMHealth(reachable=True)


def test_ask_returns_grounded_answer_with_citations_and_trace(client) -> None:
    client.post("/tenants/acme/ingest", json=_INGEST_PAYLOAD)

    response = client.post("/tenants/acme/ask", json={"question": QUESTION})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == DEFAULT_ANSWER
    assert body["found_in_corpus"] is True
    assert body["citations"]
    citation = body["citations"][0]
    assert set(citation) == {"source", "brand", "chunk_text"}
    assert citation["source"] == "synthetic://asana-1"
    assert [entry["node"] for entry in body["trace"]] == ["retrieve", "grade", "answer"]


def test_ask_returns_citations_matching_retrieved_chunks(client) -> None:
    client.post("/tenants/acme/ingest", json=_INGEST_PAYLOAD)

    body = client.post("/tenants/acme/ask", json={"question": QUESTION}).json()

    # Citations are always traceable back to the ingested source, never invented.
    assert {citation["source"] for citation in body["citations"]} == {"synthetic://asana-1"}
    assert all(citation["chunk_text"] for citation in body["citations"])


def test_ask_off_topic_question_returns_honest_not_found(make_client) -> None:
    local_client = make_client(FakeLLM(relevance=lambda _prompt: False))
    local_client.post("/tenants/acme/ingest", json=_INGEST_PAYLOAD)

    body = local_client.post("/tenants/acme/ask", json={"question": OFF_TOPIC}).json()

    assert body["found_in_corpus"] is False
    assert body["citations"] == []
    assert body["answer"] == NOT_FOUND_ANSWER
    nodes = [entry["node"] for entry in body["trace"]]
    assert nodes == ["retrieve", "grade", "rewrite", "retrieve", "grade"]


def test_ask_empty_tenant_returns_not_found_instead_of_error(client) -> None:
    # No ingestion for "globex": the workflow reports no evidence, not a 500.
    response = client.post("/tenants/globex/ask", json={"question": QUESTION})

    assert response.status_code == 200
    body = response.json()
    assert body["found_in_corpus"] is False
    assert body["citations"] == []
    assert body["answer"] == NOT_FOUND_ANSWER
    assert [entry["node"] for entry in body["trace"]] == ["retrieve", "grade"]


def test_ask_rejects_invalid_tenant_id(client) -> None:
    response = client.post("/tenants/-invalid-/ask", json={"question": QUESTION})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_tenant_id"


def test_ask_rejects_empty_question(client) -> None:
    response = client.post("/tenants/acme/ask", json={"question": ""})

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_error"


def test_ask_provider_timeout_maps_to_gateway_timeout(make_client) -> None:
    local_client = make_client(_TimeoutLLM())
    local_client.post("/tenants/acme/ingest", json=_INGEST_PAYLOAD)

    response = local_client.post("/tenants/acme/ask", json={"question": QUESTION})

    assert response.status_code == 504
    assert response.json()["code"] == "llm_timeout"
