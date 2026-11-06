"""Small async retry helper with exponential backoff.

Used for transient network/LLM failures. Retries are always bounded so the
application can never enter an infinite retry loop.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


async def with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    retries: int = 2,
    base_delay: float = 0.25,
    max_delay: float = 2.0,
    retry_on: Sequence[type[BaseException]] = (Exception,),
    description: str = "operation",
) -> T:
    """Execute ``operation`` retrying transient failures with backoff.

    Args:
        operation: Zero-argument coroutine factory to execute.
        retries: Number of *additional* attempts after the first failure.
        base_delay: Base delay in seconds, doubled on each retry.
        max_delay: Upper bound for the delay.
        retry_on: Exception types that trigger a retry.
        description: Label used in log messages.
    """
    attempt = 0
    while True:
        try:
            return await operation()
        except tuple(retry_on) as exc:
            if attempt >= retries:
                raise
            delay = min(max_delay, base_delay * (2**attempt))
            delay += random.uniform(0, base_delay)
            logger.warning(
                "%s failed, retrying",
                description,
                extra={"attempt": attempt + 1, "delay_s": round(delay, 3), "error": str(exc)},
            )
            await asyncio.sleep(delay)
            attempt += 1
