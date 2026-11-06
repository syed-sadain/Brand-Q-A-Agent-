"""Shared/common Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    """Consistent error envelope returned for every failure."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "invalid_tenant_id",
                "message": "The tenant identifier is invalid.",
            }
        }
    )

    code: str = Field(description="Stable machine readable error code.")
    message: str = Field(description="Human readable error message.")
    details: dict | None = Field(default=None, description="Optional extra context.")
