"""Dependency injection container and FastAPI dependencies.

Shared, expensive-to-build objects (LLM client, embeddings, vector store, agent)
are created lazily and cached per process. Routes depend on small ``Depends``
callables so tests can override them with fakes without touching production code.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from app.agents.brand_qa_agent import BrandQAAgent
from app.core.config import Settings, get_settings
from app.integrations.embeddings.base import BaseEmbeddings
from app.integrations.embeddings.factory import build_embeddings
from app.integrations.llm.base import BaseLLM
from app.integrations.llm.factory import build_llm
from app.integrations.vectorstores.base import BaseVectorStore
from app.integrations.vectorstores.factory import build_vector_store
from app.repositories.document_repository import DocumentRepository
from app.services.ingestion_service import IngestionService


class Container:
    """Lazily constructs and caches the application's shared dependencies."""

    def __init__(
        self,
        settings: Settings,
        *,
        llm: BaseLLM | None = None,
        embeddings: BaseEmbeddings | None = None,
        vector_store: BaseVectorStore | None = None,
        repository: DocumentRepository | None = None,
    ) -> None:
        self.settings = settings
        self._llm = llm
        self._embeddings = embeddings
        self._vector_store = vector_store
        self._repository = repository
        self._ingestion_service: IngestionService | None = None
        self._agent: BrandQAAgent | None = None

    # ------------------------------------------------------------------ providers
    def llm(self) -> BaseLLM:
        if self._llm is None:
            self._llm = build_llm(self.settings)
        return self._llm

    def embeddings(self) -> BaseEmbeddings:
        if self._embeddings is None:
            self._embeddings = build_embeddings(self.settings)
        return self._embeddings

    def vector_store(self) -> BaseVectorStore:
        if self._vector_store is None:
            self._vector_store = build_vector_store(self.settings)
        return self._vector_store

    def repository(self) -> DocumentRepository:
        if self._repository is None:
            self._repository = DocumentRepository(self.settings.document_registry_path)
        return self._repository

    # ------------------------------------------------------------------ services
    def ingestion_service(self) -> IngestionService:
        if self._ingestion_service is None:
            self._ingestion_service = IngestionService(
                settings=self.settings,
                embeddings=self.embeddings(),
                vector_store=self.vector_store(),
                repository=self.repository(),
            )
        return self._ingestion_service

    def agent(self) -> BrandQAAgent:
        if self._agent is None:
            self._agent = BrandQAAgent.build(
                settings=self.settings,
                llm=self.llm(),
                embeddings=self.embeddings(),
                vector_store=self.vector_store(),
                repository=self.repository(),
            )
        return self._agent


@lru_cache
def get_container() -> Container:
    """Return the process-wide dependency container."""
    return Container(get_settings())


def get_settings_dep() -> Settings:
    """FastAPI dependency returning the active settings."""
    return get_container().settings


def get_container_dep() -> Container:
    """FastAPI dependency returning the dependency container."""
    return get_container()


def get_ingestion_service_dep(
    container: Container = Depends(get_container_dep),
) -> IngestionService:
    """FastAPI dependency returning the ingestion service."""
    return container.ingestion_service()


def get_agent_dep(container: Container = Depends(get_container_dep)) -> BrandQAAgent:
    """FastAPI dependency returning the Brand Q&A agent."""
    return container.agent()
