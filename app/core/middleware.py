"""HTTP middleware and centralized exception handling registration."""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.exceptions import AppError
from app.core.logging import get_logger, request_id_ctx

logger = get_logger(__name__)

_REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a correlation id to every request and log its outcome."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # pragma: no cover - defensive, handlers catch AppError
            duration_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "Unhandled error",
                extra={"path": request.url.path, "duration_ms": round(duration_ms, 2)},
            )
            raise
        finally:
            request_id_ctx.reset(token)
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers[_REQUEST_ID_HEADER] = request_id
        response.headers["Server-Timing"] = f"app;dur={duration_ms:.2f}"
        logger.info(
            "request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response


def _error_response(
    status_code: int, code: str, message: str, details: dict | None = None
) -> JSONResponse:
    body: dict = {"code": code, "message": message}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    """Register consistent error responses for the whole application."""

    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        logger.warning("application error", extra={"error_code": exc.code, "detail": exc.message})
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(
            status_code=422,
            code="request_validation_error",
            message="The request payload failed validation.",
            # Validation errors can embed raw exception objects (e.g. a ValueError
            # raised by a custom model validator) which are not JSON serializable.
            details={"errors": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        logger.exception("unhandled exception", extra={"error_type": type(exc).__name__})
        return _error_response(
            status_code=500,
            code="internal_error",
            message="An internal server error occurred.",
        )
