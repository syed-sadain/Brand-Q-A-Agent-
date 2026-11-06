"""Integration tests for ``GET /health``.

The endpoint must always return HTTP 200 and report the *actual* reachability of
each dependency (healthy / degraded / unavailable) rather than merely confirming a
client object exists.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import __version__
from app.api.dependencies import Container, get_container_dep
from app.integrations.vectorstores.base import VectorStoreHealth
from app.integrations.vectorstores.memory_store import InMemoryVectorStore
from app.main import app as fastapi_app
from tests.conftest import FakeLLM


class _UnavailableVectorStore(InMemoryVectorStore):
    """A working store whose health probe reports an outage."""

    async def health_check(self) -> VectorStoreHealth:
        return VectorStoreHealth(status="unavailable", provider=self.provider, detail="simulated")


def test_health_reports_all_dependencies_healthy(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["version"] == __version__
    assert body["app_env"] == "test"
    assert set(body["components"]) == {"vector_store", "embeddings", "llm"}
    assert body["components"]["vector_store"]["provider"] == "memory"
    assert body["components"]["embeddings"]["provider"] == "hashing"
    assert all(component["status"] == "healthy" for component in body["components"].values())


def test_health_is_degraded_when_llm_is_unreachable(make_client) -> None:
    local_client = make_client(FakeLLM(health_reachable=False))

    body = local_client.get("/health").json()

    assert body["status"] == "degraded"
    assert body["components"]["llm"]["status"] == "unavailable"
    assert body["components"]["vector_store"]["status"] == "healthy"


def test_health_is_unavailable_when_vector_store_is_down(settings, embeddings, repository) -> None:
    container = Container(
        settings,
        llm=FakeLLM(),
        embeddings=embeddings,
        vector_store=_UnavailableVectorStore(dimension=settings.embedding_dimension),
        repository=repository,
    )
    previous = fastapi_app.dependency_overrides.get(get_container_dep)
    fastapi_app.dependency_overrides[get_container_dep] = lambda: container
    try:
        with TestClient(fastapi_app) as local_client:
            response = local_client.get("/health")
    finally:
        if previous is None:
            fastapi_app.dependency_overrides.pop(get_container_dep, None)
        else:
            fastapi_app.dependency_overrides[get_container_dep] = previous

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["components"]["vector_store"]["status"] == "unavailable"


def test_openapi_schema_exposes_the_three_public_endpoints(client) -> None:
    schema = client.get("/openapi.json").json()

    paths = set(schema["paths"])
    assert "/health" in paths
    assert "/tenants/{tenant_id}/ingest" in paths
    assert "/tenants/{tenant_id}/ask" in paths
