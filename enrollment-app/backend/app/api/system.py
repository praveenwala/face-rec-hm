"""System endpoints: relationship categories + audit log (contracts/rest-api.md).

GET /api/relationships — the configurable, user-supplied category list (FR-004).
GET /api/audit        — newest-first admin log; never contains image bytes/secrets.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings, parse_uuid
from app.config import Settings
from app.services.person_service import PersonService

router = APIRouter(tags=["system"])


@router.get("/api/relationships")
def relationships(settings: Settings = Depends(get_settings)) -> dict:
    return {"relationships": list(settings.relationships)}


@router.get("/api/audit")
def audit(
    person_id: str | None = None, session: Session = Depends(get_session)
) -> dict:
    if person_id is not None:
        person_id = parse_uuid(person_id, name="person id")
    return {"entries": PersonService(session).list_audit_entries(person_id)}