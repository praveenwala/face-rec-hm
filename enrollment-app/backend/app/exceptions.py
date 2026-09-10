"""Domain exceptions.

Services raise these; the API layer (``app/api/errors.py``) maps them to the
documented error envelope (contracts/rest-api.md). Codes are the canonical
``ErrorCode`` strings from ``app/models/enums.py``.
"""

from __future__ import annotations

from typing import Any

from app.models.enums import ErrorCode


class AppError(Exception):
    """Base application error carrying the machine-readable contract code."""

    status_code = 400
    code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details or {}


class StorageError(AppError):
    status_code = 500
    code = ErrorCode.STORAGE_FAILURE


class DatabaseError(AppError):
    status_code = 500
    code = ErrorCode.DATABASE_FAILURE


class NotFoundError(AppError):
    status_code = 404
    code = ErrorCode.PERSON_NOT_FOUND  # overridden per-entity by callers


class PersonNotFoundError(NotFoundError):
    code = ErrorCode.PERSON_NOT_FOUND


class PhotoNotFoundError(NotFoundError):
    code = ErrorCode.PHOTO_NOT_FOUND


class ConflictError(AppError):
    status_code = 409
    code = ErrorCode.IDENTITY_CONFLICT


class ValidationAppError(AppError):
    status_code = 400
    code = ErrorCode.VALIDATION_ERROR


class FeatureNotEnabledError(AppError):
    """Explicit 501 for unimplemented future phases (Phase 6 enrollment routes)."""

    status_code = 501
    code = ErrorCode.FEATURE_NOT_ENABLED


class FaceDetectorUnavailableError(AppError):
    """Phase 4: the approved YuNet detector is missing/unloadable. Analysis fails
    cleanly with this 503 — there is NO silent fallback detector (user-approved
    decision; readiness semantics must never silently change detector)."""

    status_code = 503
    code = ErrorCode.FACE_DETECTOR_UNAVAILABLE