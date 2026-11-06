"""Unit tests for LLM-based relevance grading."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.core.exceptions import LLMError
from app.integrations.llm.base import BaseLLM, LLMHealth, LLMMessage
from app.models.document import RetrievedChunk
from app.services.grading_service import GradingService
from tests.conftest import FakeLLM


def _chunk(index: int, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        id=f"doc-1-{index}",
        text=text,
        score=1.0 - index * 0.1,
        tenant_id="acme",
        doc_id="doc-1",
        chunk_index=index,
        source="https://example.com/article",
        brand="Asana",
        content_hash="h" * 64,
    )


class SelectiveLLM(BaseLLM):
    """Fails structured calls for prompts containing a marker string."""

    provider = "fake"
    model = "fake"
    fail_marker = "GARDENING"

    async def ainvoke(self, messages: list[LLMMessage]) -> str:
        return "unused"

    async def ainvoke_structured(self, messages: list[LLMMessage], schema: type[BaseModel]):
        if self.fail_marker in messages[-1].content:
            raise LLMError("provider exploded")
        return schema(relevant=True)

    async def health_check(self) -> LLMHealth:
        return LLMHealth(reachable=True)


async def test_all_relevant_chunks_are_kept() -> None:
    outcome = await GradingService(FakeLLM()).grade("pricing question", [_chunk(0, "pricing")])
    assert len(outcome.relevant) == 1
    assert outcome.rejected_count == 0


async def test_irrelevant_chunks_are_rejected() -> None:
    service = GradingService(FakeLLM(relevance=lambda _prompt: False))
    chunks = [_chunk(0, "pricing"), _chunk(1, "pricing")]
    outcome = await service.grade("pricing question", chunks)
    assert outcome.relevant == []
    assert outcome.rejected_count == 2


async def test_grading_splits_relevant_and_irrelevant() -> None:
    # The grading prompt includes the question, so the predicate keys off the chunk
    # content (the gardening marker) rather than the question text.
    service = GradingService(FakeLLM(relevance=lambda prompt: "gardening" not in prompt))
    chunks = [_chunk(0, "pricing details"), _chunk(1, "gardening details")]
    outcome = await service.grade("pricing question", chunks)
    assert [chunk.chunk_index for chunk in outcome.relevant] == [0]
    assert outcome.rejected_count == 1


async def test_no_chunks_returns_empty_outcome() -> None:
    outcome = await GradingService(FakeLLM()).grade("anything", [])
    assert outcome.relevant == []
    assert outcome.rejected_count == 0


async def test_partial_grading_failures_count_as_rejected() -> None:
    service = GradingService(SelectiveLLM())
    chunks = [_chunk(0, "pricing details"), _chunk(1, "GARDENING details")]
    outcome = await service.grade("pricing question", chunks)
    assert [chunk.chunk_index for chunk in outcome.relevant] == [0]
    assert outcome.rejected_count == 1


async def test_total_grading_failure_raises_llm_error() -> None:
    service = GradingService(FakeLLM(fail_all_grading=True))
    with pytest.raises(LLMError):
        await service.grade("pricing question", [_chunk(0, "pricing"), _chunk(1, "pricing")])
