"""Domain exceptions.

Services raise these; the API layer (``app/api/errors.py``) maps them to the
documented error envelope (contracts/rest-api.md). Codes are the canonical
``ErrorCode`` strings from ``app/models/enums.py``.

This is the SINGLE application error framework. Phase 6 (Frigate enrollment)
exceptions are added here as ``AppError`` subclasses using the same
``ErrorCode`` enum — there is no second error framework.
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


# ---------------------------------------------------------------------------
# Phase 1–5 (canonical, unchanged)
# ---------------------------------------------------------------------------


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


class PhotoNotApprovableError(ConflictError):
    """Phase 5: approval attempted on a photo whose quality_status is not SUITABLE.
    Only SUITABLE photos may be explicitly approved (contract photo-quality.md);
    PENDING/UNSUITABLE/REVIEW_REQUIRED are refused loudly, never silently ignored."""

    code = ErrorCode.PHOTO_NOT_APPROVABLE


class ValidationAppError(AppError):
    status_code = 400
    code = ErrorCode.VALIDATION_ERROR


class FeatureNotEnabledError(AppError):
    """Explicit 501 for features disabled at runtime (Phase 6 enrollment routes when
    FRIGATE_ENROLLMENT_ENABLED is false). This is the controlled refusal."""

    status_code = 501
    code = ErrorCode.FEATURE_NOT_ENABLED


class FaceDetectorUnavailableError(AppError):
    """Phase 4: the approved YuNet detector is missing/unloadable. Analysis fails
    cleanly with this 503 — there is NO silent fallback detector (user-approved
    decision; readiness semantics must never silently change detector)."""

    status_code = 503
    code = ErrorCode.FACE_DETECTOR_UNAVAILABLE


# ---------------------------------------------------------------------------
# Feature 002 Phase 6 — Frigate enrollment (same framework, same ErrorCode enum)
# ---------------------------------------------------------------------------


class EnrollmentNotReadyError(ConflictError):
    """Enrollment requested for a person who is not READY (or is disabled)."""

    status_code = 409
    code = ErrorCode.NOT_READY


class IdentityConflictError(ConflictError):
    """A conflicting Frigate identity name already exists (local table or Frigate)."""

    status_code = 409
    code = ErrorCode.IDENTITY_CONFLICT


class FrigateUnavailableError(AppError):
    """Frigate management API is unreachable or not responding."""

    status_code = 503
    code = ErrorCode.FRIGATE_UNAVAILABLE


class FrigateAuthError(AppError):
    """Frigate rejected credentials / authentication failed."""

    status_code = 502
    code = ErrorCode.FRIGATE_AUTH_FAILED


class FrigateEnrollmentError(AppError):
    """A mutating Frigate face operation failed."""

    status_code = 502
    code = ErrorCode.FRIGATE_ENROLLMENT_FAILURE


class ReconciliationRequiredError(AppError):
    """Local and external (Frigate) enrollment state disagree; manual reconciliation
    is required. Raised when rollback could not fully restore external state, or when
    reconcile() detects drift that must not be auto-resolved."""

    status_code = 409
    code = ErrorCode.RECONCILIATION_REQUIRED


class EnrollmentInProgressError(ConflictError):
    """Another enrollment/removal for this person is already in progress (per-person
    concurrency guard). Second concurrent caller is rejected safely."""

    status_code = 409
    code = ErrorCode.ENROLLMENT_IN_PROGRESS
