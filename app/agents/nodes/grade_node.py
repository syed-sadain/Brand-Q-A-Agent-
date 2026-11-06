"""Grade node: let the LLM decide which retrieved chunks are actually relevant."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.agents.graph_state import GraphState, dependencies_from_config
from app.core.logging import get_logger
from app.schemas.citation import TraceEntry

logger = get_logger(__name__)


async def grade_node(state: GraphState, config: RunnableConfig) -> dict:
    """Grade every retrieved chunk and keep only the relevant ones.

    Grading uses the user's original question so that a rewritten query can never
    widen what counts as relevant to the user's actual intent.
    """
    dependencies = dependencies_from_config(config)
    question = state["question"]
    chunks = state.get("retrieved_chunks", [])

    outcome = await dependencies.grading.grade(question, chunks)
    detail = f"{len(outcome.relevant)} relevant, {outcome.rejected_count} rejected"
    logger.info("grade node", extra={"relevant": len(outcome.relevant)})
    return {
        "relevant_chunks": outcome.relevant,
        "trace": [TraceEntry(node="grade", detail=detail)],
    }
