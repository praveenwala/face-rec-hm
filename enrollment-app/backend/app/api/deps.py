"""Shared FastAPI dependencies (session, settings, UUID parsing)."""

from __future__ import annotations

import uuid

from fastapi import Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.exceptions import ValidationAppError
from app.models.enums import ErrorCode


def get_session(request: Request):
    """One session per request, closed when the request finishes."""
    factory = request.app.state.session_factory
    with factory() as session:
        yield session


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def parse_uuid(value: str, *, name: str = "id") -> str:
    """Reject malformed UUIDs with an explicit VALIDATION_ERROR (contracts/rest-api.md).

    Unknown-but-valid UUIDs are handled later by the service (404 PERSON_NOT_FOUND);
    malformed values are a client error and never reach the database.
    """
    try:
        uuid.UUID(value)
    except ValueError:
        raise ValidationAppError(
            f"Invalid {name}: {value!r} is not a valid UUID",
            code=ErrorCode.VALIDATION_ERROR,
        )
    return value