"""``GET /health`` — dependency reachability endpoint."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from app import __version__
from app.api.dependencies import Container, get_container_dep
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.integrations.embeddings.base import BaseEmbeddings
from app.integrations.llm.base import BaseLLM
from app.integrations.vectorstores.base import BaseVectorStore
from app.schemas.health import ComponentHealth, ComponentStatus, HealthResponse

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


async def _check_vector_store(store: BaseVectorStore) -> ComponentHealth:
    started = time.perf_counter()
    health = await store.health_check()
    return ComponentHealth(
        status=health.status,
        provider=health.provider,
        detail=health.detail,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
    )


async def _check_embeddings(embeddings: BaseEmbeddings) -> ComponentHealth:
    started = time.perf_counter()
    health = await embeddings.health_check()
    return ComponentHealth(
        status="healthy" if health.reachable else "unavailable",
        provider=embeddings.provider,
        detail=health.detail,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
    )


async def _check_llm(llm: BaseLLM) -> ComponentHealth:
    started = time.perf_counter()
    health = await llm.health_check()
    return ComponentHealth(
        status="healthy" if health.reachable else "unavailable",
        provider=llm.provider,
        detail=health.detail,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service and dependency health",
    description=(
        "Always returns HTTP 200 and reports the *actual* reachability of the vector "
        "database, the embedding provider and the LLM provider. A dependency is never "
        "reported healthy merely because its client was constructed."
    ),
)
async def health_check(container: Container = Depends(get_container_dep)) -> HealthResponse:
    """Report the reachability of the service's critical dependencies."""
    settings = container.settings
    components: dict[str, ComponentHealth] = {}

    try:
        components["vector_store"] = await _check_vector_store(container.vector_store())
    except AppError as exc:
        components["vector_store"] = ComponentHealth(
            status="unavailable", provider=settings.vector_store_provider, detail=exc.message
        )

    try:
        components["embeddings"] = await _check_embeddings(container.embeddings())
    except AppError as exc:
        components["embeddings"] = ComponentHealth(
            status="unavailable", provider=settings.embedding_provider, detail=exc.message
        )

    try:
        components["llm"] = await _check_llm(container.llm())
    except AppError as exc:
        components["llm"] = ComponentHealth(
            status="unavailable", provider=settings.llm_provider, detail=exc.message
        )

    overall: ComponentStatus
    if components["vector_store"].status == "unavailable":
        overall = "unavailable"
    elif any(component.status != "healthy" for component in components.values()):
        overall = "degraded"
    else:
        overall = "healthy"

    return HealthResponse(
        status=overall,
        app_env=settings.app_env,
        version=__version__,
        components=components,
    )
