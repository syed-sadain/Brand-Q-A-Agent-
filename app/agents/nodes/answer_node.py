"""Answer node: produce a grounded answer and citations from relevant chunks."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.agents.graph_state import GraphState, dependencies_from_config
from app.core.logging import get_logger
from app.schemas.citation import TraceEntry

logger = get_logger(__name__)


async def answer_node(state: GraphState, config: RunnableConfig) -> dict:
    """Answer the original question using only the relevant chunks."""
    dependencies = dependencies_from_config(config)
    question = state["question"]
    chunks = state.get("relevant_chunks", [])

    answer = await dependencies.answer.generate_answer(question, chunks)
    citations = dependencies.citations.build(chunks)
    logger.info("answer node", extra={"citations": len(citations)})
    return {
        "answer": answer,
        "citations": citations,
        "found_in_corpus": True,
        "trace": [
            TraceEntry(node="answer", detail=f"Answer generated from {len(chunks)} relevant chunks")
        ],
    }
