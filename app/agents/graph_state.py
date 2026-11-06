"""Strongly typed LangGraph state and dependency container.

The state is a ``TypedDict`` so it is explicit and inspectable. ``trace`` uses an
``operator.add`` reducer, which lets every node *append* its own entry instead of
overwriting the trace — this is what makes the returned trace a genuine record of
the executed workflow.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from langchain_core.runnables import RunnableConfig

from app.models.document import RetrievedChunk
from app.schemas.citation import Citation, TraceEntry
from app.services.answer_service import AnswerService
from app.services.citation_service import CitationService
from app.services.grading_service import GradingService
from app.services.retrieval_service import RetrievalService


class GraphState(TypedDict, total=False):
    """State passed between LangGraph nodes."""

    tenant_id: str
    question: str
    rewritten_question: str
    retrieved_chunks: list[RetrievedChunk]
    relevant_chunks: list[RetrievedChunk]
    retry_count: int
    corpus_empty: bool
    answer: str
    found_in_corpus: bool
    citations: list[Citation]
    trace: Annotated[list[TraceEntry], operator.add]


@dataclass(slots=True)
class GraphDependencies:
    """Services injected into the graph nodes at invocation time."""

    retrieval: RetrievalService
    grading: GradingService
    answer: AnswerService
    citations: CitationService


def dependencies_from_config(config: RunnableConfig | None) -> GraphDependencies:
    """Extract the injected :class:`GraphDependencies` from a runnable config."""
    if not config:
        raise RuntimeError("Graph dependencies were not supplied in the runnable config.")
    configurable: dict[str, Any] = config.get("configurable") or {}
    dependencies = configurable.get("dependencies")
    if not isinstance(dependencies, GraphDependencies):
        raise RuntimeError("Invalid graph configuration: 'dependencies' is missing.")
    return dependencies
