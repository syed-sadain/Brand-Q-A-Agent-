"""FastAPI application entry point.

Run with::

    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware, register_exception_handlers

logger = get_logger(__name__)

_DESCRIPTION = """
Multi-tenant **Brand Q&A** backend.

* `POST /tenants/{tenant_id}/ingest` — ingest URL or raw-text documents.
* `POST /tenants/{tenant_id}/ask` — ask a question about a tenant's corpus.
* `GET  /health` — dependency reachability.

Answers are produced by a LangGraph workflow (retrieve → grade → answer, with one
rewrite/retry) and are strictly limited to a tenant's own documents.
"""


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "application starting",
        extra={
            "app_env": settings.app_env,
            "vector_store": settings.vector_store_provider,
            "llm_provider": settings.llm_provider,
            "embedding_provider": settings.embedding_provider,
        },
    )
    yield
    logger.info("application shutting down")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.log_json)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=_DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
