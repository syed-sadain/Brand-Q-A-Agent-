"""Shared pytest fixtures and deterministic fakes.

The whole suite is designed to run **without any LLM API key**: a deterministic
:class:`FakeLLM` replaces the provider, ``hashing`` embeddings replace the
embedding provider, and an in-memory vector store plus an ephemeral document
registry replace the external infrastructure.

Nothing here reaches the network.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:  # allow `pytest` to be run without `python -m`
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.agents.brand_qa_agent import BrandQAAgent
from app.api.dependencies import Container, get_container_dep
from app.core.config import Settings
from app.integrations.embeddings.base import BaseEmbeddings
from app.integrations.embeddings.factory import build_embeddings
from app.integrations.llm.base import BaseLLM, LLMHealth, LLMMessage
from app.integrations.vectorstores.base import BaseVectorStore
from app.integrations.vectorstores.factory import build_vector_store
from app.main import app as fastapi_app
from app.repositories.document_repository import DocumentRepository
from app.schemas.ingest import IngestDocumentRequest
from app.services.ingestion_service import IngestionService

# Deterministic hashing-embedding dimension (must be small to stay fast).
DIMENSION = 256

DEFAULT_ANSWER = "Reviewers describe Asana as pricier than Trello for small teams."
DEFAULT_REWRITE = "asana trello pricing comparison reviewers"

# --------------------------------------------------------------------------- corpus
ASANA_DOC = (
    "Asana and Trello pricing review. Reviewers frequently note that Asana's per-seat "
    "pricing becomes expensive for larger teams, while Trello offers a generous free tier "
    "and cheaper paid plans. Comparison articles describe Asana as more powerful for complex "
    "workflows but say Trello is better value for small teams. Pricing for Asana starts at a "
    "higher monthly per-user rate than Trello's entry plan. Reviewers recommend Trello for "
    "budget-conscious small teams and Asana for structured project portfolios."
)

TRELLO_DOC = (
    "Trello is often recommended for small teams because its board-based interface is simple "
    "to learn and its entry pricing is low. Reviewers say Trello's free tier is generous, "
    "though advanced automation and reporting require a paid plan. Several articles compare "
    "Trello with Asana and conclude that Trello wins on price and simplicity, while Asana wins "
    "on depth of project planning features."
)

NOTION_DOC = (
    "Notion combines documents, wikis and lightweight databases in a single workspace. "
    "Reviewers describe Notion as flexible and strong for knowledge management, while noting "
    "that its project management views are less specialised than dedicated tools. Pricing "
    "articles say Notion's personal plan is free and its team plan is priced per member."
)

UNRELATED_DOC = (
    "Hydroponic gardening guide. Leafy greens such as lettuce and spinach grow well in "
    "nutrient solutions with pH between five and six. Tomatoes require more light and "
    "calcium. Gardeners should change the reservoir weekly and monitor electrical "
    "conductivity to avoid nutrient burn."
)


class FakeLLM(BaseLLM):
    """Deterministic, offline LLM double.

    * ``ainvoke`` returns the configured *answer* for answer prompts and the
      configured *rewrite* for rewrite prompts (branched on the prompt text).
    * ``ainvoke_structured`` returns a :class:`GradingDecision` driven by the
      ``relevance`` predicate, which keeps grading decisions controllable and
      realistic instead of echoing a fixed value.
    """

    provider = "fake"
    model = "fake-model"

    def __init__(
        self,
        *,
        relevance: Callable[[str], bool] | None = None,
        answer: str = DEFAULT_ANSWER,
        rewrite: str = DEFAULT_REWRITE,
        fail_all_grading: bool = False,
        health_reachable: bool = True,
    ) -> None:
        self._relevance = relevance or (lambda _prompt: True)
        self._answer = answer
        self._rewrite = rewrite
        self._fail_all_grading = fail_all_grading
        self._health_reachable = health_reachable

        self.answer_calls = 0
        self.rewrite_calls = 0
        self.grading_calls = 0

    async def ainvoke(self, messages: list[LLMMessage]) -> str:
        prompt = messages[-1].content
        if "Rewrite the question" in prompt:
            self.rewrite_calls += 1
            return self._rewrite
        self.answer_calls += 1
        return self._answer

    async def ainvoke_structured(self, messages: list[LLMMessage], schema: type[BaseModel]):
        self.grading_calls += 1
        if self._fail_all_grading:
            from app.core.exceptions import LLMError

            raise LLMError("simulated grading failure")
        prompt = messages[-1].content
        return schema(relevant=bool(self._relevance(prompt)), reason="fake decision")

    async def health_check(self) -> LLMHealth:
        return LLMHealth(
            reachable=self._health_reachable, detail=None if self._health_reachable else "down"
        )


# --------------------------------------------------------------------------- fixtures
@pytest.fixture
def settings() -> Settings:
    """Settings tuned for fast, deterministic, fully offline tests."""
    return Settings(
        app_env="test",
        app_name="Brand Q&A Agent (test)",
        vector_store_provider="memory",
        embedding_provider="hashing",
        embedding_dimension=DIMENSION,
        chunk_size=40,
        chunk_overlap=8,
        retrieval_top_k=5,
        http_timeout=5.0,
        http_max_bytes=1_000_000,
        log_level="WARNING",
    )


@pytest.fixture
def embeddings(settings: Settings) -> BaseEmbeddings:
    return build_embeddings(settings)


@pytest.fixture
def vector_store(settings: Settings) -> BaseVectorStore:
    return build_vector_store(settings)


@pytest.fixture
def repository() -> DocumentRepository:
    """Ephemeral (in-process) document registry — no file I/O."""
    return DocumentRepository(path=None)


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def ingestion_service(
    settings: Settings,
    embeddings: BaseEmbeddings,
    vector_store: BaseVectorStore,
    repository: DocumentRepository,
) -> IngestionService:
    return IngestionService(
        settings=settings,
        embeddings=embeddings,
        vector_store=vector_store,
        repository=repository,
    )


@pytest.fixture
def make_agent(
    settings: Settings,
    embeddings: BaseEmbeddings,
    vector_store: BaseVectorStore,
    repository: DocumentRepository,
) -> Callable[[BaseLLM], BrandQAAgent]:
    """Build a :class:`BrandQAAgent` wired to the shared test doubles."""

    def _make(llm: BaseLLM) -> BrandQAAgent:
        return BrandQAAgent.build(
            settings=settings,
            llm=llm,
            embeddings=embeddings,
            vector_store=vector_store,
            repository=repository,
        )

    return _make


@pytest.fixture
def agent(make_agent: Callable[[BaseLLM], BrandQAAgent], fake_llm: FakeLLM) -> BrandQAAgent:
    return make_agent(fake_llm)


@pytest.fixture
def make_client(
    settings: Settings,
    embeddings: BaseEmbeddings,
    vector_store: BaseVectorStore,
    repository: DocumentRepository,
) -> Iterator[Callable[[BaseLLM], TestClient]]:
    """Return a factory that serves the real FastAPI app with injected fakes."""
    created: list[TestClient] = []

    def _make(llm: BaseLLM) -> TestClient:
        container = Container(
            settings,
            llm=llm,
            embeddings=embeddings,
            vector_store=vector_store,
            repository=repository,
        )
        fastapi_app.dependency_overrides[get_container_dep] = lambda: container
        client = TestClient(fastapi_app)
        created.append(client)
        return client

    yield _make

    fastapi_app.dependency_overrides.clear()
    for client in created:
        client.close()


@pytest.fixture
def client(make_client: Callable[[BaseLLM], TestClient], fake_llm: FakeLLM) -> TestClient:
    return make_client(fake_llm)


@pytest.fixture
def allow_all_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass DNS resolution in the SSRF check so HTTP fetching is fully offline.

    Structural SSRF validation (scheme/host/IP-literal checks) is exercised
    separately in ``tests/unit/test_security.py``; here we only need the fetch
    plumbing to work against ``respx`` mocks.
    """

    async def _allow(url: str, _settings: Settings) -> str:
        return url

    monkeypatch.setattr("app.pipelines.document_loader.validate_url_async", _allow)


# --------------------------------------------------------------------------- helpers
async def ingest(
    service: IngestionService,
    tenant_id: str,
    documents: list[IngestDocumentRequest],
):
    """Small convenience wrapper used across the test-suite."""
    return await service.ingest(tenant_id, documents)


def raw_document(text: str, brand: str, source: str) -> IngestDocumentRequest:
    return IngestDocumentRequest(text=text, brand=brand, source=source)
