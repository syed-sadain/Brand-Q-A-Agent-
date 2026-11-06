"""Aggregates all v1 route modules into a single router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import ask, health, ingest

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(ingest.router)
api_router.include_router(ask.router)

__all__ = ["api_router"]
