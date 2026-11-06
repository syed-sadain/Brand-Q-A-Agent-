"""Concrete embedding providers."""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from itertools import pairwise

from app.core.exceptions import EmbeddingError
from app.core.logging import get_logger
from app.integrations.embeddings.base import BaseEmbeddings, EmbeddingHealth

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_BATCH_SIZE = 64


class LangChainEmbeddings(BaseEmbeddings):
    """Adapter around any LangChain ``Embeddings`` implementation."""

    def __init__(self, *, provider: str, model: str, dimension: int, embeddings: object) -> None:
        self.provider = provider
        self.model = model
        self.dimension = dimension
        self._embeddings = embeddings

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            vectors: list[list[float]] = []
            for start in range(0, len(texts), _BATCH_SIZE):
                batch = texts[start : start + _BATCH_SIZE]
                vectors.extend(await self._embeddings.aembed_documents(batch))  # type: ignore[attr-defined]
            return vectors
        except Exception as exc:
            logger.error(
                "embedding batch failed", extra={"provider": self.provider, "error": str(exc)}
            )
            raise EmbeddingError("Failed to generate embeddings.") from exc

    async def aembed_query(self, text: str) -> list[float]:
        try:
            return await self._embeddings.aembed_query(text)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.error(
                "embedding query failed", extra={"provider": self.provider, "error": str(exc)}
            )
            raise EmbeddingError("Failed to embed the query.") from exc

    async def health_check(self) -> EmbeddingHealth:
        try:
            await self.aembed_query("health probe")
            return EmbeddingHealth(reachable=True)
        except EmbeddingError as exc:
            return EmbeddingHealth(reachable=False, detail=exc.message)


class HashingEmbeddings(BaseEmbeddings):
    """Deterministic local embedding for offline development and tests.

    This is a *feature hashing* bag-of-words embedding. It is intentionally cheap
    and dependency-free so the test-suite and local demos can run without any API
    key. It captures lexical overlap (not deep semantics) and must not be used as
    a substitute for a real embedding model in production.
    """

    provider = "hashing"

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self.model = f"hashing-{dimension}"

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = _TOKEN_RE.findall(text.lower())
        features = tokens + [f"{a}_{b}" for a, b in pairwise(tokens)]
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % self.dimension
            sign = 1.0 if (value >> 63) & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(component * component for component in vector))
        if norm > 0:
            vector = [component / norm for component in vector]
        return vector

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        await asyncio.sleep(0)  # keep the async contract without blocking
        return [self._embed(text) for text in texts]

    async def aembed_query(self, text: str) -> list[float]:
        await asyncio.sleep(0)
        return self._embed(text)

    async def health_check(self) -> EmbeddingHealth:
        return EmbeddingHealth(reachable=True, detail="local deterministic embeddings")
