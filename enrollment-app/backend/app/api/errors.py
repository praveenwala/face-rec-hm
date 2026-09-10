"""Error envelope + FastAPI exception handlers (contracts/rest-api.md).

Every error response shape:

    {"error": {"code": "...", "message": "...", "details": {...}}}

Domain exceptions (app/exceptions.py) map to documented codes; validation errors map
to VALIDATION_ERROR; anything else maps to INTERNAL_ERROR (logged, never leaking
internals to the client).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.exceptions import AppError
from app.models.enums import ErrorCode

logger = logging.getLogger(__name__)


def error_payload(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _json_safe(value: Any) -> Any:
    """Strip non-JSON-serializable objects (e.g. exceptions embedded in Pydantic's
    ``ctx``) so validation details always serialize cleanly."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Exception):
        return {"type": type(value).__name__, "message": str(value)}
    try:
        import json

        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)

def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code.value, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=error_payload(
                ErrorCode.VALIDATION_ERROR.value,
                "Request validation failed",
                {"errors": _json_safe(exc.errors())},
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content=error_payload(
                ErrorCode.INTERNAL_ERROR.value, "Internal server error"
            ),
        )