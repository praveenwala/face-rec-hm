"""People endpoints (Phase 2, contracts/rest-api.md).

POST  /api/people          — create (never enrolls anything)
GET   /api/people          — flat summary list; grouping happens in the frontend
GET   /api/people/{id}     — detail
PATCH /api/people/{id}     — display_name / relationship / enabled only
DELETE /api/people/{id}    — 204, or 409 ENROLLED_PERSON_DELETE_REFUSED when enrolled
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_session, parse_uuid
from app.schemas import PersonCreate, PersonUpdate
from app.services.person_service import PersonService

router = APIRouter(prefix="/api/people", tags=["people"])


def _service(session: Session = Depends(get_session)) -> PersonService:
    return PersonService(session)


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
def delete_person(person_id: str, service: PersonService = Depends(_service)) -> Response:
    # Phase 2: `remove_enrollment` is NOT honored — biometric removal is Phase 6, and
    # refusing while ENROLLED is the only way to guarantee no orphaned enrollment.
    service.delete(parse_uuid(person_id, name="person id"))
    return Response(status_code=204)