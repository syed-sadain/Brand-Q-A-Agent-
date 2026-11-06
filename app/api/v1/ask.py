"""``POST /tenants/{tenant_id}/ask`` — grounded question answering endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from app.agents.brand_qa_agent import BrandQAAgent
from app.api.dependencies import get_agent_dep
from app.core.security import validate_tenant_id
from app.schemas.ask import AskRequest, AskResponse
from app.schemas.common import ErrorResponse

router = APIRouter(tags=["question answering"])


@router.post(
    "/tenants/{tenant_id}/ask",
    response_model=AskResponse,
    summary="Ask a question about a tenant's ingested corpus",
    description=(
        "Runs the LangGraph workflow: retrieve the top 5 tenant-scoped chunks, grade "
        "them for relevance with the LLM, optionally rewrite the question and retry "
        "once, then answer strictly from relevant evidence. When nothing relevant is "
        "found, ``found_in_corpus`` is false, ``citations`` is empty and the actual "
        "workflow trace is still returned."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Invalid tenant identifier."},
        504: {"model": ErrorResponse, "description": "The LLM provider timed out."},
        503: {"model": ErrorResponse, "description": "The vector database is unavailable."},
        422: {"model": ErrorResponse, "description": "The request body failed validation."},
    },
)
async def ask_question(
    payload: AskRequest,
    tenant_id: str = Path(description="Tenant identifier", examples=["acme"]),
    agent: BrandQAAgent = Depends(get_agent_dep),
) -> AskResponse:
    """Answer ``payload.question`` using only the tenant's ingested documents."""
    validated_tenant = validate_tenant_id(tenant_id)
    return await agent.ask(validated_tenant, payload.question)
