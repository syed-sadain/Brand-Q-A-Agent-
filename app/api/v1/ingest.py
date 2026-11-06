"""``POST /tenants/{tenant_id}/ingest`` — document ingestion endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from app.api.dependencies import get_ingestion_service_dep
from app.core.security import validate_tenant_id
from app.schemas.common import ErrorResponse
from app.schemas.ingest import IngestError, IngestRequest, IngestResponse
from app.services.ingestion_service import IngestionService

router = APIRouter(tags=["ingestion"])


@router.post(
    "/tenants/{tenant_id}/ingest",
    response_model=IngestResponse,
    summary="Ingest documents for a tenant",
    description=(
        "Accepts URL-based or raw-text documents, extracts and normalises content, "
        "chunks it, embeds the chunks and upserts them into the tenant's isolated "
        "vector namespace. Re-ingesting the same document overwrites its vectors "
        "instead of duplicating them."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Invalid tenant id or unsafe URL."},
        502: {"model": ErrorResponse, "description": "A document URL could not be fetched."},
        503: {"model": ErrorResponse, "description": "The vector database is unavailable."},
        422: {"model": ErrorResponse, "description": "The request body failed validation."},
    },
)
async def ingest_documents(
    payload: IngestRequest,
    tenant_id: str = Path(description="Tenant identifier", examples=["acme"]),
    service: IngestionService = Depends(get_ingestion_service_dep),
) -> IngestResponse:
    """Ingest one or more documents for ``tenant_id``."""
    validated_tenant = validate_tenant_id(tenant_id)
    result = await service.ingest(validated_tenant, payload.documents)
    return IngestResponse(
        documents_stored=result.documents_stored,
        chunks_stored=result.chunks_stored,
        errors=[IngestError(**error) for error in result.errors],
    )
