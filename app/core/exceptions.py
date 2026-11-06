"""Application specific exceptions.

Every error surfaced to a client maps to a stable ``code`` and an HTTP status
code so that API responses stay consistent. Internal details (stack traces,
secrets) are never included in the response payload.
"""

from __future__ import annotations

from http import HTTPStatus


class AppError(Exception):
    """Base class for all expected application errors."""

    code: str = "internal_error"
    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, *, details: dict | None = None) -> None:
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        payload: dict = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


# --------------------------------------------------------------------- input
class DocumentInputError(AppError):
    """Raised when a document payload is structurally invalid."""

    code = "invalid_document_input"
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    message = "The document input is invalid."


class EmptyDocumentError(AppError):
    """Raised when a document yields no usable text after extraction."""

    code = "empty_document"
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    message = "The document contains no usable text."


class InvalidTenantError(AppError):
    """Raised when the tenant identifier fails validation."""

    code = "invalid_tenant_id"
    status_code = HTTPStatus.BAD_REQUEST
    message = "The tenant identifier is invalid."


class UnsafeUrlError(AppError):
    """Raised when a URL is unsafe to fetch (SSRF protection)."""

    code = "unsafe_url"
    status_code = HTTPStatus.BAD_REQUEST
    message = "The provided URL is not allowed."


# --------------------------------------------------------------------- external
class DocumentFetchError(AppError):
    """Raised when a remote document cannot be retrieved."""

    code = "document_fetch_failed"
    status_code = HTTPStatus.BAD_GATEWAY
    message = "Failed to fetch the document from the provided URL."


class LLMError(AppError):
    """Raised when the LLM provider fails."""

    code = "llm_error"
    status_code = HTTPStatus.BAD_GATEWAY
    message = "The language model provider returned an error."


class LLMTimeoutError(LLMError):
    """Raised when the LLM provider times out."""

    code = "llm_timeout"
    status_code = HTTPStatus.GATEWAY_TIMEOUT
    message = "The language model provider timed out."


class VectorStoreError(AppError):
    """Raised when the vector database fails."""

    code = "vector_store_error"
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    message = "The vector database is unavailable."


class EmbeddingError(AppError):
    """Raised when embedding generation fails."""

    code = "embedding_error"
    status_code = HTTPStatus.BAD_GATEWAY
    message = "Failed to generate embeddings."


# --------------------------------------------------------------------- domain
class EmptyCorpusError(AppError):
    """Raised when a tenant has no indexed documents."""

    code = "empty_corpus"
    status_code = HTTPStatus.NOT_FOUND
    message = "No documents have been ingested for this tenant."


class ConfigurationError(AppError):
    """Raised when the application is misconfigured."""

    code = "configuration_error"
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    message = "The application is misconfigured."
