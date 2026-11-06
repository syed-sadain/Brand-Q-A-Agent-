"""Builds and compiles the Brand Q&A LangGraph ``StateGraph``."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.edges.conditional_edges import ANSWER_NODE, route_after_grade
from app.agents.graph_state import GraphState
from app.agents.nodes.answer_node import answer_node
from app.agents.nodes.grade_node import grade_node
from app.agents.nodes.retrieve_node import retrieve_node
from app.agents.nodes.rewrite_node import rewrite_node


def build_graph() -> CompiledStateGraph:
    """Create and compile the question-answering graph.

    Flow::

        START -> retrieve -> grade -> (answer | rewrite -> retrieve | END)
    """
    builder = StateGraph(GraphState)

    builder.add_node("retrieve", retrieve_node)
    builder.add_node("grade", grade_node)
    builder.add_node("rewrite", rewrite_node)
    builder.add_node(ANSWER_NODE, answer_node)

    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "grade")
    builder.add_conditional_edges(
        "grade",
        route_after_grade,
        {ANSWER_NODE: ANSWER_NODE, "rewrite": "rewrite", END: END},
    )
    builder.add_edge("rewrite", "retrieve")
    builder.add_edge(ANSWER_NODE, END)

    return builder.compile()
