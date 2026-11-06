"""Ingestion request/response schemas."""

from __future__ import annotations

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


class IngestDocumentRequest(BaseModel):
    """A single document to ingest.

    Exactly one content source must be provided: either a ``url`` (fetched by the
    service) or raw ``text`` (used directly).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://example.com/best-pm-tools-2026",
                "brand": "Asana",
            }
        }
    )

    url: AnyHttpUrl | None = Field(default=None, description="Web page URL to fetch and extract.")
    text: str | None = Field(default=None, min_length=1, description="Raw document text.")
    source: str | None = Field(
        default=None,
        max_length=512,
        description="Optional source label. Required for raw text to keep citations meaningful.",
    )
    brand: str = Field(min_length=1, max_length=128, description="Brand the document discusses.")

    @model_validator(mode="after")
    def _exactly_one_source(self) -> IngestDocumentRequest:
        has_url = self.url is not None
        has_text = self.text is not None and bool(self.text.strip())
        if has_url == has_text:
            raise ValueError("Each document must provide exactly one of 'url' or 'text'.")
        if has_text and not self.source:
            # A stable, human readable label keeps citations meaningful for raw text.
            self.source = f"manual-{abs(hash(self.text)) % 10**8:08d}"
        return self


class IngestRequest(BaseModel):
    """Body of ``POST /tenants/{tenant_id}/ingest``."""

    documents: list[IngestDocumentRequest] = Field(
        min_length=1, max_length=100, description="Documents to ingest (1-100)."
    )


class IngestError(BaseModel):
    """Per-document failure detail returned alongside partial successes."""

    source: str = Field(description="Source identifier of the document that failed.")
    code: str = Field(description="Machine readable failure code.")
    message: str = Field(description="Human readable failure message.")


class IngestResponse(BaseModel):
    """Body of the ingestion response."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"documents_stored": 2, "chunks_stored": 37}}
    )

    documents_stored: int = Field(ge=0, description="Number of documents stored (upserted).")
    chunks_stored: int = Field(ge=0, description="Number of chunks stored (upserted).")
    errors: list[IngestError] = Field(
        default_factory=list, description="Documents that could not be ingested."
    )
