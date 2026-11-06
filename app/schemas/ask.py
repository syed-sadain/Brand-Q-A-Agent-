"""Question answering request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.citation import Citation, TraceEntry


class AskRequest(BaseModel):
    """Body of ``POST /tenants/{tenant_id}/ask``."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "What do reviewers say about Asana's pricing compared to Trello?"
            }
        }
    )

    question: str = Field(
        min_length=1, max_length=1000, description="Natural language question about the corpus."
    )


class AskResponse(BaseModel):
    """Answer payload, always grounded in the retrieved corpus."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "Reviewers generally describe Asana as powerful but pricier than Trello.",
                "found_in_corpus": True,
                "citations": [
                    {
                        "source": "https://example.com/best-pm-tools-2026",
                        "brand": "Asana",
                        "chunk_text": "Asana's per-seat pricing scales quickly for larger teams...",
                    }
                ],
                "trace": [
                    {"node": "retrieve", "detail": "5 chunks retrieved"},
                    {"node": "grade", "detail": "3 relevant, 2 rejected"},
                    {"node": "answer", "detail": "Answer generated from 3 relevant chunks"},
                ],
            }
        }
    )

    answer: str = Field(description="Grounded answer, or an explicit not-found message.")
    found_in_corpus: bool = Field(description="True only when usable evidence was found.")
    citations: list[Citation] = Field(
        default_factory=list, description="Evidence backing the answer."
    )
    trace: list[TraceEntry] = Field(
        default_factory=list, description="Actual graph execution trace."
    )
