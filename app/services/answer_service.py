"""Grounded answer generation and question rewriting."""

from __future__ import annotations

from app.core.logging import get_logger
from app.integrations.llm.base import BaseLLM, LLMMessage
from app.models.document import RetrievedChunk
from app.services.prompts import (
    GROUNDED_ANSWER_SYSTEM_PROMPT,
    REWRITE_SYSTEM_PROMPT,
    build_answer_prompt,
    build_rewrite_prompt,
)

logger = get_logger(__name__)


class AnswerService:
    """Generate grounded answers and retrieval-friendly question rewrites."""

    def __init__(self, llm: BaseLLM) -> None:
        self._llm = llm

    async def generate_answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        """Answer ``question`` using only ``chunks`` as evidence."""
        messages = [
            LLMMessage(role="system", content=GROUNDED_ANSWER_SYSTEM_PROMPT),
            LLMMessage(role="user", content=build_answer_prompt(question, chunks)),
        ]
        answer = await self._llm.ainvoke(messages)
        logger.info("answer generated", extra={"evidence_chunks": len(chunks)})
        return answer.strip()

    async def rewrite_question(self, question: str) -> str:
        """Rewrite ``question`` to improve semantic retrieval.

        Falls back to the original question if the model returns nothing usable.
        """
        messages = [
            LLMMessage(role="system", content=REWRITE_SYSTEM_PROMPT),
            LLMMessage(role="user", content=build_rewrite_prompt(question)),
        ]
        rewritten = (await self._llm.ainvoke(messages)).strip()
        if not rewritten:
            return question
        return rewritten.splitlines()[0].strip() or question
