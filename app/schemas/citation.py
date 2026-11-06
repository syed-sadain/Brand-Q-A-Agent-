"""Citation and trace schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    """A reference back to the evidence an answer was grounded in."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source": "https://example.com/best-pm-tools-2026",
                "brand": "Asana",
                "chunk_text": "Reviewers note that Asana's per-seat pricing scales quickly...",
            }
        }
    )

    source: str = Field(description="Original source URL or label of the evidence.")
    brand: str = Field(description="Brand the cited chunk belongs to.")
    chunk_text: str = Field(description="Verbatim excerpt from the retrieved chunk.")


class TraceEntry(BaseModel):
    """A single node execution record produced by the LangGraph workflow."""

    node: str = Field(description="Name of the node that appended this entry.")
    detail: str = Field(description="Human readable description of what the node did.")
