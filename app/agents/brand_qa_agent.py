"""The Brand Q&A agent: wires services into the compiled LangGraph graph."""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from app.agents.graph_builder import build_graph
from app.agents.graph_state import GraphDependencies, GraphState
from app.core.config import Settings
from app.core.logging import get_logger
from app.integrations.embeddings.base import BaseEmbeddings
from app.integrations.llm.base import BaseLLM
from app.integrations.vectorstores.base import BaseVectorStore
from app.repositories.document_repository import DocumentRepository
from app.schemas.ask import AskResponse
from app.services.answer_service import AnswerService
from app.services.citation_service import NOT_FOUND_ANSWER, CitationService
from app.services.grading_service import GradingService
from app.services.retrieval_service import RetrievalService

logger = get_logger(__name__)


class BrandQAAgent:
    """Runs the LangGraph question-answering workflow for a tenant."""

    def __init__(
        self,
        *,
        graph: CompiledStateGraph,
        dependencies: GraphDependencies,
        settings: Settings,
    ) -> None:
        self._graph = graph
        self._dependencies = dependencies
        self._settings = settings

    @classmethod
    def build(
        cls,
        *,
        settings: Settings,
        llm: BaseLLM,
        embeddings: BaseEmbeddings,
        vector_store: BaseVectorStore,
        repository: DocumentRepository,
    ) -> BrandQAAgent:
        """Construct the agent and its dependency graph."""
        dependencies = GraphDependencies(
            retrieval=RetrievalService(
                vector_store=vector_store,
                embeddings=embeddings,
                repository=repository,
                settings=settings,
            ),
            grading=GradingService(llm),
            answer=AnswerService(llm),
            citations=CitationService(),
        )
        return cls(graph=build_graph(), dependencies=dependencies, settings=settings)

    # ------------------------------------------------------------------ api
    def get_graph(self) -> Any:
        """Expose the compiled graph so it can be inspected/visualised."""
        return self._graph.get_graph()

    async def ask(self, tenant_id: str, question: str) -> AskResponse:
        """Run the workflow and return a grounded, tenant-scoped answer."""
        initial_state: GraphState = {
            "tenant_id": tenant_id,
            "question": question,
            "rewritten_question": "",
            "retrieved_chunks": [],
            "relevant_chunks": [],
            "retry_count": 0,
            "answer": "",
            "found_in_corpus": False,
            "citations": [],
            "trace": [],
        }
        config: RunnableConfig = {"configurable": {"dependencies": self._dependencies}}
        final_state = await self._graph.ainvoke(initial_state, config)

        found = bool(final_state.get("found_in_corpus"))
        answer = (final_state.get("answer") or "").strip() or NOT_FOUND_ANSWER
        citations = final_state.get("citations") or []
        trace = final_state.get("trace") or []

        if not found:
            # Never return citations or an LLM answer when there is no evidence.
            citations = []
            answer = NOT_FOUND_ANSWER

        logger.info(
            "ask completed",
            extra={
                "tenant_id": tenant_id,
                "found_in_corpus": found,
                "citations": len(citations),
                "nodes_executed": len(trace),
            },
        )
        return AskResponse(answer=answer, found_in_corpus=found, citations=citations, trace=trace)
