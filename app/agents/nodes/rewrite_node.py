"""Rewrite node: improve the question for a single retrieval retry."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.agents.graph_state import GraphState, dependencies_from_config
from app.core.logging import get_logger
from app.schemas.citation import TraceEntry

logger = get_logger(__name__)


async def rewrite_node(state: GraphState, config: RunnableConfig) -> dict:
    """Rewrite the question to improve retrieval and increment ``retry_count``.

    The rewritten question always derives from the user's *original* question so
    intent is preserved across retries.
    """
    dependencies = dependencies_from_config(config)
    original = state["question"]
    rewritten = await dependencies.answer.rewrite_question(original)
    retry_count = state.get("retry_count", 0) + 1
    logger.info("rewrite node", extra={"retry_count": retry_count})
    return {
        "rewritten_question": rewritten,
        "retry_count": retry_count,
        "trace": [
            TraceEntry(
                node="rewrite", detail=f"Question rewritten and retry #{retry_count} scheduled"
            )
        ],
    }
