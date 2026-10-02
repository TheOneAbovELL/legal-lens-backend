"""Consistent, non-leaky error responses."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError
from app.core.logging import get_logger, request_id_var
from app.schemas.common import ErrorResponse

logger = get_logger(__name__)


def _err(description: str, code: str, message: str) -> dict:
    return {"model": ErrorResponse, "description": description, "content": {"application/json": {"example": {
        "error": {"code": code, "message": message, "request_id": "3f1c9a7e2b8d4c55a6f0e1d2c3b4a596"}}}}}


#: OpenAPI documentation of the structured error responses returned by the handlers below.
ERROR_RESPONSES: dict[int | str, dict] = {
    401: _err("Missing, invalid or expired bearer token", "authentication_failed", "Invalid or missing credentials."),
    403: _err("Not allowed", "forbidden", "Self-registration is disabled."),
    404: _err("Not found (or not owned by the caller) / disabled", "not_found", "The requested resource was not found."),
    409: _err("Conflict", "conflict", "Username or email is already registered."),
    413: _err("Request body too large", "payload_too_large", "Request body is too large."),
    422: _err("Validation error", "validation_error", "The request is invalid."),
    429: _err("Rate limit exceeded (see Retry-After)", "rate_limited", "Too many requests. Please retry later."),
    502: _err("LLM provider failure after retries/fallback", "llm_provider_error",
              "The language model provider failed to respond."),
    503: _err("A required dependency is unavailable", "vector_store_error", "The document index is unavailable."),
    504: _err("Pipeline timeout", "timeout", "The request took too long to process."),
}


def responses(*codes: int) -> dict[int | str, dict]:
    return {code: ERROR_RESPONSES[code] for code in codes}


def _body(code: str, message: str, details: list[dict] | None = None) -> dict:
    error: dict = {"code": code, "message": message, "request_id": request_id_var.get()}
    if details:
        error["details"] = details
    return {"error": error}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        level = logger.error if exc.http_status >= 500 else logger.info
        level("request failed", extra={"error_category": exc.code, "status": exc.http_status, "error": str(exc)[:500]})
        headers = {}
        if getattr(exc, "retry_after", None):
            headers["Retry-After"] = str(exc.retry_after)  # type: ignore[attr-defined]
        if exc.http_status == 401:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(_body(exc.code, exc.public_message), status_code=exc.http_status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")}
            for e in exc.errors()
        ]
        return JSONResponse(_body("validation_error", "The request is invalid.", details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed", 413: "payload_too_large"}.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(_body(code, message), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error", extra={"error_type": type(exc).__name__})
        return JSONResponse(_body("internal_error", "An internal error occurred."), status_code=500)
