"""Retrieve node: embed the question and fetch the top chunks for the tenant."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.agents.graph_state import GraphState, dependencies_from_config
from app.core.exceptions import EmptyCorpusError
from app.core.logging import get_logger
from app.schemas.citation import TraceEntry

logger = get_logger(__name__)


async def retrieve_node(state: GraphState, config: RunnableConfig) -> dict:
    """Retrieve the top-k chunks for the current question within the tenant.

    The active question is the rewritten one when a retry has happened, otherwise
    the user's original question.
    """
    dependencies = dependencies_from_config(config)
    tenant_id = state["tenant_id"]
    question = state.get("rewritten_question") or state["question"]

    corpus_empty = False
    try:
        chunks = await dependencies.retrieval.search(tenant_id, question)
        detail = f"{len(chunks)} chunks retrieved" if chunks else "0 chunks retrieved (no matches)"
    except EmptyCorpusError:
        chunks = []
        corpus_empty = True
        detail = "0 chunks retrieved (tenant has no documents)"

    logger.info("retrieve node", extra={"tenant_id": tenant_id, "chunks": len(chunks)})
    return {
        "retrieved_chunks": chunks,
        "corpus_empty": corpus_empty,
        "trace": [TraceEntry(node="retrieve", detail=detail)],
    }
