"""Provider-agnostic chat LLM interface.

Business logic (graph nodes, services) depends only on this interface, which
keeps the LLM provider swappable and trivially mockable in tests.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal, TypeVar

from pydantic import BaseModel, Field

StructuredT = TypeVar("StructuredT", bound=BaseModel)

Role = Literal["system", "user", "assistant"]


class LLMMessage(BaseModel):
    """A single chat message."""

    role: Role
    content: str


class LLMHealth(BaseModel):
    """Result of an LLM reachability probe."""

    reachable: bool
    detail: str | None = None


class BaseLLM(ABC):
    """Interface every chat LLM provider must implement."""

    provider: str
    model: str

    @abstractmethod
    async def ainvoke(self, messages: list[LLMMessage]) -> str:
        """Return the assistant's text response for ``messages``."""

    @abstractmethod
    async def ainvoke_structured(
        self, messages: list[LLMMessage], schema: type[StructuredT]
    ) -> StructuredT:
        """Return a validated instance of ``schema`` extracted from the response."""

    @abstractmethod
    async def health_check(self) -> LLMHealth:
        """Perform a real, cheap round-trip to confirm reachability."""

    @staticmethod
    def system(content: str) -> LLMMessage:
        return LLMMessage(role="system", content=content)

    @staticmethod
    def user(content: str) -> LLMMessage:
        return LLMMessage(role="user", content=content)


class GradingDecision(BaseModel):
    """Structured output schema for the relevance grading node."""

    relevant: bool = Field(description="True if the chunk helps answer the question.")
    reason: str = Field(default="", description="Short justification for the decision.")
