"""Relevance grading service.

The LLM is asked, per retrieved chunk, whether the chunk helps answer the
question. Only chunks that the model marks relevant are kept, so retrieval
similarity alone never determines relevance.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.core.exceptions import LLMError
from app.core.logging import get_logger
from app.integrations.llm.base import BaseLLM, GradingDecision, LLMMessage
from app.models.document import RetrievedChunk
from app.services.prompts import GRADING_SYSTEM_PROMPT, build_grading_prompt

logger = get_logger(__name__)


@dataclass(slots=True)
class GradingOutcome:
    """Result of grading a batch of chunks."""

    relevant: list[RetrievedChunk] = field(default_factory=list)
    rejected_count: int = 0


class GradingService:
    """Grade retrieved chunks for relevance using the configured LLM."""

    def __init__(self, llm: BaseLLM, *, max_concurrency: int = 5) -> None:
        self._llm = llm
        self._max_concurrency = max(1, max_concurrency)

    async def grade(self, question: str, chunks: list[RetrievedChunk]) -> GradingOutcome:
        """Return the relevant chunks and how many were rejected.

        Raises:
            LLMError: when *every* grading call fails (e.g. provider outage/timeout),
                so the API can return a clear error instead of a false "not found".
        """
        if not chunks:
            return GradingOutcome()

        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def _grade_one(chunk: RetrievedChunk) -> bool:
            async with semaphore:
                messages = [
                    LLMMessage(role="system", content=GRADING_SYSTEM_PROMPT),
                    LLMMessage(role="user", content=build_grading_prompt(question, chunk)),
                ]
                decision = await self._llm.ainvoke_structured(messages, GradingDecision)
                return decision.relevant

        results = await asyncio.gather(
            *(_grade_one(chunk) for chunk in chunks), return_exceptions=True
        )

        outcome = GradingOutcome()
        failures: list[BaseException] = []
        for chunk, result in zip(chunks, results, strict=True):
            if isinstance(result, BaseException):
                failures.append(result)
                continue
            if result:
                outcome.relevant.append(chunk)
            else:
                outcome.rejected_count += 1

        if failures:
            logger.warning("grading failed for some chunks", extra={"failures": len(failures)})
            outcome.rejected_count += len(failures)
            if len(failures) == len(chunks):
                first = failures[0]
                if isinstance(first, LLMError):
                    raise first
                raise LLMError("Relevance grading failed for every retrieved chunk.")

        logger.info(
            "grading completed",
            extra={"relevant": len(outcome.relevant), "rejected": outcome.rejected_count},
        )
        return outcome
