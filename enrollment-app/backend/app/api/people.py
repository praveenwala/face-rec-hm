"""People endpoints (Phase 2–5, contracts/rest-api.md).

POST  /api/people          — create (never enrolls anything)
GET   /api/people          — flat summary list; grouping happens in the frontend
GET   /api/people/{id}     — detail
GET   /api/people/{id}/readiness — Phase 5 enrollment-readiness payload
PATCH /api/people/{id}     — display_name / relationship / enabled only
DELETE /api/people/{id}    — 204, or 409 ENROLLED_PERSON_DELETE_REFUSED when enrolled;
                             removes the person's private photo files (Phase 3)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings, parse_uuid
from app.config import Settings
from app.schemas import PersonCreate, PersonUpdate
from app.services.person_service import PersonService
from app.services.photo_service import PhotoService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/people", tags=["people"])


def _service(session: Session = Depends(get_session)) -> PersonService:
    return PersonService(session)


def _photo_service(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> PhotoService:
    return PhotoService(session, settings)


@router.get("")
def list_people(service: PersonService = Depends(_service)) -> dict:
    people = service.list()
    return {"people": [service.to_summary(p) for p in people]}


@router.post("", status_code=201)
def create_person(body: PersonCreate, service: PersonService = Depends(_service)) -> dict:
    person = service.create(body.display_name, body.relationship.value)
    return service.to_detail(person)


@router.get("/{person_id}")
def get_person(person_id: str, service: PersonService = Depends(_service)) -> dict:
    person = service.get(parse_uuid(person_id, name="person id"))
    return service.to_detail(person)


@router.get("/{person_id}/readiness")
def get_readiness(
    person_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Phase 5 enrollment readiness (contracts/photo-quality.md). READY means the
    local manager holds >= 5 approved suitable non-duplicate photos — it never
    implies enrollment (Phase 6 remains blocked)."""
    from app.services.readiness_service import ReadinessService

    return ReadinessService(session, settings).readiness(
        parse_uuid(person_id, name="person id")
    )


@router.patch("/{person_id}")
def update_person(
    person_id: str, body: PersonUpdate, service: PersonService = Depends(_service)
) -> dict:
    person = service.update(
        parse_uuid(person_id, name="person id"),
        display_name=body.display_name,
        relationship=body.relationship.value if body.relationship is not None else None,
        enabled=body.enabled,
    )
    return service.to_detail(person)


@router.delete("/{person_id}", status_code=204)
def delete_person(
    person_id: str,
    service: PersonService = Depends(_service),
    photo_service: PhotoService = Depends(_photo_service),
) -> Response:
    # Phase 2/3: `remove_enrollment` is NOT honored — biometric removal is Phase 6, and
    # refusing while ENROLLED is the only way to guarantee no orphaned enrollment.
    pid = parse_uuid(person_id, name="person id")
    service.delete(pid)
    try:
        photo_service.delete_person_files(pid)
    except Exception as exc:  # best effort — DB delete already committed
        logger.warning("Person %s deleted but private files could not be removed: %s", pid, exc)
    return Response(status_code=204)