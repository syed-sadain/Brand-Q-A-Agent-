"""MANDATORY TEST 2 — LangGraph decision logic.

All three conditions required by the assignment are exercised against the real
compiled ``StateGraph`` (not a re-implementation):

1. Relevant chunks found            -> answer node.
2. No relevant chunks, first attempt -> rewrite and retry (exactly once).
3. No relevant chunks after retry    -> not found.
"""

from __future__ import annotations

from langgraph.graph import END

from app.agents.edges.conditional_edges import ANSWER_NODE, route_after_grade
from app.services.citation_service import NOT_FOUND_ANSWER
from tests.conftest import ASANA_DOC, DEFAULT_ANSWER, FakeLLM, ingest, raw_document

QUESTION = "What do reviewers say about Asana's pricing compared to Trello?"
OFF_TOPIC = "What is the capital of France?"


def _trace_nodes(response) -> list[str]:
    return [entry.node for entry in response.trace]


# ------------------------------------------------------------------ routing unit
def test_route_to_answer_when_relevant_chunks_exist() -> None:
    state = {"relevant_chunks": [object()], "retry_count": 0}
    assert route_after_grade(state) == ANSWER_NODE


def test_route_to_rewrite_when_no_relevant_chunks_and_no_retry() -> None:
    state = {"relevant_chunks": [], "retry_count": 0}
    assert route_after_grade(state) == "rewrite"


def test_route_to_end_when_no_relevant_chunks_after_retry() -> None:
    state = {"relevant_chunks": [], "retry_count": 1}
    assert route_after_grade(state) == END


def test_route_prefers_answer_over_retry_when_chunks_are_relevant() -> None:
    state = {"relevant_chunks": [object()], "retry_count": 1}
    assert route_after_grade(state) == ANSWER_NODE


# ------------------------------------------------------------------ graph structure
def test_graph_exposes_the_expected_nodes(make_agent, fake_llm: FakeLLM) -> None:
    graph = make_agent(fake_llm).get_graph()
    assert {"retrieve", "grade", "rewrite", ANSWER_NODE} <= set(graph.nodes)


# ------------------------------------------------------------- condition 1: answer
async def test_mandatory_relevant_chunks_route_to_answer(ingestion_service, make_agent) -> None:
    await ingest(
        ingestion_service, "acme", [raw_document(ASANA_DOC, "Asana", "synthetic://asana-1")]
    )
    llm = FakeLLM(relevance=lambda _prompt: True)
    agent = make_agent(llm)

    response = await agent.ask("acme", QUESTION)

    assert _trace_nodes(response) == ["retrieve", "grade", "answer"]
    assert response.found_in_corpus is True
    assert response.answer == DEFAULT_ANSWER
    assert response.citations
    assert llm.rewrite_calls == 0


# --------------------------------------------- condition 2 + 3: rewrite / not found
async def test_mandatory_no_relevant_first_attempt_triggers_rewrite_and_retry(
    ingestion_service, make_agent
) -> None:
    await ingest(
        ingestion_service, "acme", [raw_document(ASANA_DOC, "Asana", "synthetic://asana-1")]
    )
    llm = FakeLLM(relevance=lambda _prompt: False)
    agent = make_agent(llm)

    response = await agent.ask("acme", OFF_TOPIC)
    nodes = _trace_nodes(response)

    # The question is rewritten once and retrieval is retried exactly once.
    assert nodes.count("rewrite") == 1
    assert nodes.count("retrieve") == 2
    assert llm.rewrite_calls == 1


async def test_mandatory_no_relevant_after_retry_returns_not_found(
    ingestion_service, make_agent
) -> None:
    await ingest(
        ingestion_service, "acme", [raw_document(ASANA_DOC, "Asana", "synthetic://asana-1")]
    )
    agent = make_agent(FakeLLM(relevance=lambda _prompt: False))

    response = await agent.ask("acme", OFF_TOPIC)

    assert response.found_in_corpus is False
    assert response.citations == []
    assert response.answer == NOT_FOUND_ANSWER
    # The real execution trace is preserved even though no answer was produced.
    assert "answer" not in _trace_nodes(response)
    assert _trace_nodes(response) == ["retrieve", "grade", "rewrite", "retrieve", "grade"]


async def test_only_one_retry_is_performed(ingestion_service, make_agent) -> None:
    """A persistently empty retrieval must never loop: retrieval runs at most twice."""
    await ingest(
        ingestion_service, "acme", [raw_document(ASANA_DOC, "Asana", "synthetic://asana-1")]
    )
    llm = FakeLLM(relevance=lambda _prompt: False)
    agent = make_agent(llm)

    response = await agent.ask("acme", OFF_TOPIC)

    assert _trace_nodes(response).count("retrieve") <= 2
    assert _trace_nodes(response).count("rewrite") <= 1
    assert llm.rewrite_calls == 1


async def test_empty_tenant_never_reaches_the_answer_node(make_agent) -> None:
    llm = FakeLLM()
    agent = make_agent(llm)
    response = await agent.ask("globex", QUESTION)
    assert response.found_in_corpus is False
    assert response.citations == []
    assert "answer" not in _trace_nodes(response)
    assert _trace_nodes(response) == ["retrieve", "grade"]
    assert llm.rewrite_calls == 0
