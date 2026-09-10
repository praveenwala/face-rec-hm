"""Phase 6 enrollment routes — explicitly NOT enabled (spec FR-030, contracts/rest-api.md).

These stubs return 501 FEATURE_NOT_ENABLED so the API surface is honest and the UI can
render visibly disabled controls. They never fake a successful enrollment and never
touch Frigate. Phase 6 remains BLOCKED pending explicit user approval.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.exceptions import FeatureNotEnabledError

router = APIRouter(prefix="/api", tags=["enrollment-future"])

_PHASE6_NOTE = "Frigate enrollment is not enabled in this phase (Feature 002 Phase 6 is blocked)."


@router.post("/people/{person_id}/enroll")
def enroll_person(person_id: str) -> None:
    raise FeatureNotEnabledError(_PHASE6_NOTE)


@router.delete("/people/{person_id}/enrollment")
def remove_enrollment(person_id: str) -> None:
    raise FeatureNotEnabledError(_PHASE6_NOTE)


@router.get("/frigate/status")
def frigate_status() -> None:
    raise FeatureNotEnabledError(_PHASE6_NOTE)