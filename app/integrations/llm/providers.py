"""LangChain backed chat LLM providers.

Only the LangChain *chat model* abstraction is used here. Everything above this
module talks to :class:`~app.integrations.llm.base.BaseLLM`, so no LangChain
types leak into services or graph nodes.
"""

from __future__ import annotations

import asyncio
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from app.core.exceptions import LLMError, LLMTimeoutError
from app.core.logging import get_logger
from app.integrations.llm.base import BaseLLM, LLMHealth, LLMMessage

logger = get_logger(__name__)

StructuredT = TypeVar("StructuredT", bound=BaseModel)

_ROLE_MAP: dict[str, type[BaseMessage]] = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
}


class LangChainLLM(BaseLLM):
    """A :class:`BaseLLM` implementation backed by any LangChain chat model."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        chat_model: BaseChatModel,
        timeout: float,
    ) -> None:
        self.provider = provider
        self.model = model
        self._chat_model = chat_model
        self._timeout = timeout

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _to_langchain(messages: list[LLMMessage]) -> list[BaseMessage]:
        return [_ROLE_MAP[m.role](content=m.content) for m in messages]

    async def _call(self, coro: Any, *, what: str) -> Any:
        try:
            return await asyncio.wait_for(coro, timeout=self._timeout)
        except TimeoutError as exc:
            raise LLMTimeoutError(
                f"The LLM provider timed out after {self._timeout}s during {what}."
            ) from exc
        except Exception as exc:
            logger.error("LLM call failed", extra={"provider": self.provider, "error": str(exc)})
            raise LLMError(f"The LLM provider failed during {what}.") from exc

    # ------------------------------------------------------------------ api
    async def ainvoke(self, messages: list[LLMMessage]) -> str:
        response = await self._call(
            self._chat_model.ainvoke(self._to_langchain(messages)), what="completion"
        )
        content = getattr(response, "content", response)
        if isinstance(content, list):  # some providers return content blocks
            content = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in content
            )
        return str(content).strip()

    async def ainvoke_structured(
        self, messages: list[LLMMessage], schema: type[StructuredT]
    ) -> StructuredT:
        structured_model = self._chat_model.with_structured_output(schema)
        result = await self._call(
            structured_model.ainvoke(self._to_langchain(messages)), what="structured completion"
        )
        if isinstance(result, schema):
            return result
        return schema.model_validate(result)

    async def health_check(self) -> LLMHealth:
        """Send a minimal prompt to verify the provider is actually reachable."""
        try:
            await self._call(
                self._chat_model.ainvoke([HumanMessage(content="ping")]),
                what="health check",
            )
            return LLMHealth(reachable=True)
        except LLMTimeoutError as exc:
            return LLMHealth(reachable=False, detail=f"timeout: {exc.message}")
        except LLMError as exc:
            return LLMHealth(reachable=False, detail=exc.message)
