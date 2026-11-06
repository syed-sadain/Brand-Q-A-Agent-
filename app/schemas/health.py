"""Health check schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ComponentStatus = Literal["healthy", "degraded", "unavailable"]


class ComponentHealth(BaseModel):
    """Reachability of a single dependency."""

    status: ComponentStatus = Field(description="Reachability of this dependency.")
    provider: str = Field(description="Backend name, e.g. 'pinecone' or 'openai'.")
    detail: str | None = Field(default=None, description="Optional diagnostic message.")
    latency_ms: float | None = Field(default=None, description="Round-trip check latency.")


class HealthResponse(BaseModel):
    """Aggregate health of the service and its critical dependencies."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "app_env": "local",
                "version": "1.0.0",
                "components": {
                    "vector_store": {"status": "healthy", "provider": "memory"},
                    "llm": {"status": "healthy", "provider": "openai"},
                },
            }
        }
    )

    status: ComponentStatus = Field(description="Overall service status.")
    app_env: str = Field(description="Active environment name.")
    version: str = Field(description="Application version.")
    components: dict[str, ComponentHealth] = Field(description="Per-dependency statuses.")
