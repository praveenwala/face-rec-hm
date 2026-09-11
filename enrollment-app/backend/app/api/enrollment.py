"""Feature 002 Phase 6 — enrollment routes (SINGLE SOURCE OF TRUTH).

This module owns exactly three routes; they are registered ONLY here (the old 501
stubs in ``future.py`` are retired). Raw Frigate calls never appear here — all Frigate
interaction goes through ``EnrollmentService`` → ``FrigateEnrollmentService``.

    GET    /api/frigate/status                gated read-only status
    POST   /api/people/{id}/enroll            gated by FRIGATE_ENROLLMENT_ENABLED
    DELETE /api/people/{id}/enrollment        gated by FRIGATE_ENROLLMENT_ENABLED

Feature-flag behavior: while FRIGATE_ENROLLMENT_ENABLED is false the service raises
``FeatureNotEnabledError`` (canonical error framework → 501 FEATURE_NOT_ENABLED) and
performs ZERO Frigate mutation. All errors are ``AppError`` subclasses rendered by the
single canonical error handler (app/api/errors.py) — no HTTPException, no second
error framework.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings, parse_uuid
from app.config import Settings
from app.services.enrollment_service import EnrollmentService
from app.services.frigate_service import FrigateEnrollmentService

_LOG = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["feature-002-phase-6-enrollment"])


def _enrollment_service(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> EnrollmentService:
    # No real Frigate transport is wired at the API layer yet: while the feature flag
    # is OFF the service refuses before any transport use, and a real transport will be
    # injected here when the feature is enabled in a controlled environment.
    return EnrollmentService(session=session, settings=settings)


def _frigate_service(settings: Settings = Depends(get_settings)) -> FrigateEnrollmentService:
    return FrigateEnrollmentService(settings=settings, transport=None)


@router.get("/frigate/status")
def frigate_status(
    service: FrigateEnrollmentService = Depends(_frigate_service),
) -> dict[str, Any]:
    """Frigate enrollment status. Controlled refusal (501 FEATURE_NOT_ENABLED) while
    the feature flag is OFF; read-only snapshot when enabled. Never mutates."""
    service._require_enabled("frigate_status")
    return service.status()


@router.post("/people/{person_id}/enroll")
def enroll_person(
    person_id: str,
    service: EnrollmentService = Depends(_enrollment_service),
) -> dict[str, Any]:
    """Enroll a READY, enabled person into Frigate (explicit user action only).

    While FRIGATE_ENROLLMENT_ENABLED is false this refuses with FEATURE_NOT_ENABLED and
    performs zero Frigate mutation.
    """
    return service.enroll(parse_uuid(person_id, name="person id"))


@router.delete("/people/{person_id}/enrollment")
def remove_enrollment(
    person_id: str,
    service: EnrollmentService = Depends(_enrollment_service),
) -> dict[str, Any]:
    """Remove a person's Frigate enrollment (explicit user action only).

    While FRIGATE_ENROLLMENT_ENABLED is false this refuses with FEATURE_NOT_ENABLED and
    performs zero Frigate mutation.
    """
    return service.remove_enrollment(parse_uuid(person_id, name="person id"))
