"""Conditional routing for the Brand Q&A graph.

Exactly the logic required by the specification:

* relevant chunks found        -> ``answer``
* nothing relevant, no retry yet -> ``rewrite`` (one retry)
* nothing relevant after retry  -> ``END`` with ``found_in_corpus = False``

Note: LangGraph reserves state keys as node names, and ``answer`` is a required
state field, so the answer node is registered as ``generate_answer``. The trace
label it writes remains ``answer``.
"""

from __future__ import annotations

from langgraph.graph import END

from app.agents.graph_state import GraphState

ANSWER_NODE = "generate_answer"


def route_after_grade(state: GraphState) -> str:
    """Return the next node name after the grade node has run."""
    if state.get("relevant_chunks"):
        return ANSWER_NODE
    if state.get("corpus_empty", False):
        return END
    if state.get("retry_count", 0) == 0:
        return "rewrite"
    return END
