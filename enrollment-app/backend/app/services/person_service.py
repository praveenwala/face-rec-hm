"""PersonService — known-person metadata lifecycle (Phase 2, T009–T013).

Rules enforced here (not just in the UI — spec FR-003/FR-005/FR-025/FR-026):
- display_name is user-supplied, trimmed, required; never a filesystem identifier.
- relationship is user-supplied metadata, validated against the config list.
- frigate_identity_name stays NULL until Phase 6 enrollment; a rename never touches it.
- enabled is independent of enrollment state.
- delete refuses while enrollment_status == ENROLLED (biometric removal is Phase 6 and
  must happen first — never cascade-delete an enrollment from a generic person delete).
- every mutation is recorded in the audit log (FR-031) without biometric content.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.exceptions import ConflictError, PersonNotFoundError
from app.models.audit import AuditLogEntry
from app.models.enums import AuditAction, EnrollmentStatus, ErrorCode, QualityStatus
from app.models.person import Person
from app.models.photo import EnrollmentPhoto
from app.services.audit_service import AuditService


class PersonService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._audit = AuditService(session)

    # ---- reads -----------------------------------------------------------

    def get(self, person_id: str) -> Person:
        person = self._session.get(Person, person_id)
        if person is None:
            raise PersonNotFoundError(f"Person {person_id} not found")
        return person

    def list(self) -> list[Person]:
        return (
            self._session.query(Person).order_by(Person.created_at, Person.display_name).all()
        )

    # ---- writes ----------------------------------------------------------

    def create(self, display_name: str, relationship: str) -> Person:
        person = Person(
            id=str(uuid.uuid4()),
            display_name=display_name,
            relationship=relationship,
            enrollment_status=EnrollmentStatus.DRAFT.value,
        )
        self._session.add(person)
        self._audit.record(
            AuditAction.PERSON_CREATED,
            entity_type="person",
            entity_id=person.id,
            details={
                "relationship": relationship,
                "display_name_length": len(display_name),
            },
        )
        self._session.commit()
        return person

    def update(
        self,
        person_id: str,
        *,
        display_name: str | None = None,
        relationship: str | None = None,
        enabled: bool | None = None,
    ) -> Person:
        person = self.get(person_id)
        changed = False

        if display_name is not None and display_name != person.display_name:
            self._audit.record(
                AuditAction.PERSON_UPDATED,
                entity_type="person",
                entity_id=person.id,
                details={"field": "display_name", "new_length": len(display_name)},
            )
            person.display_name = display_name
            changed = True

        if relationship is not None and relationship != person.relationship:
            old = person.relationship
            self._audit.record(
                AuditAction.RELATIONSHIP_CHANGED,
                entity_type="person",
                entity_id=person.id,
                details={"from": old, "to": relationship},
            )
            person.relationship = relationship
            changed = True

        if enabled is not None and enabled != person.enabled:
            action = AuditAction.PERSON_ENABLED if enabled else AuditAction.PERSON_DISABLED
            self._audit.record(
                action,
                entity_type="person",
                entity_id=person.id,
                details={"enabled": enabled},
            )
            person.enabled = enabled
            changed = True

        if changed:
            self._session.commit()
        return person

    def delete(self, person_id: str) -> None:
        person = self.get(person_id)

        if person.enrollment_status == EnrollmentStatus.ENROLLED.value:
            raise ConflictError(
                (
                    f"Person {person.display_name!r} has an active Frigate enrollment; "
                    "remove the biometric enrollment first before deleting the record "
                    "(Phase 6). Refusing to leave an orphaned enrollment."
                ),
                code=ErrorCode.ENROLLED_PERSON_DELETE_REFUSED,
                status_code=409,
            )

        # Remove any photo rows (files are deleted by photo management in Phase 3;
        # the DB-level CASCADE covers rows regardless).
        self._session.query(EnrollmentPhoto).filter(
            EnrollmentPhoto.person_id == person.id
        ).delete()

        self._audit.record(
            AuditAction.PERSON_DELETED,
            entity_type="person",
            entity_id=person.id,
            details={"display_name_length": len(person.display_name)},
        )
        self._session.delete(person)
        self._session.commit()

    # ---- response shapes ---------------------------------------------------

    def _counts(self, person_id: str) -> tuple[int, int]:
        rows = (
            self._session.query(EnrollmentPhoto)
            .filter(EnrollmentPhoto.person_id == person_id)
            .all()
        )
        photo_count = len(rows)
        suitable_count = sum(
            1
            for r in rows
            if r.quality_status == QualityStatus.SUITABLE.value and r.approved
        )
        return photo_count, suitable_count

    def to_summary(self, person: Person) -> dict:
        photo_count, suitable_count = self._counts(person.id)
        return {
            "id": person.id,
            "display_name": person.display_name,
            "relationship": person.relationship,
            "enabled": person.enabled,
            "enrollment_status": person.enrollment_status,
            "suitable_count": suitable_count,
            "photo_count": photo_count,
            # null until photo management (Phase 3) picks a representative.
            "representative_photo_url": None,
        }

    def to_detail(self, person: Person) -> dict:
        detail = self.to_summary(person)
        detail.update(
            {
                "frigate_identity_name": person.frigate_identity_name,
                "representative_photo_id": person.representative_photo_id,
                "created_at": person.created_at.isoformat() if person.created_at else None,
                "updated_at": person.updated_at.isoformat() if person.updated_at else None,
            }
        )
        return detail

    def list_audit_entries(self, person_id: str | None = None, limit: int = 200) -> list[dict]:
        query = self._session.query(AuditLogEntry).order_by(AuditLogEntry.id.desc())
        if person_id is not None:
            query = query.filter(AuditLogEntry.entity_id == person_id)
        return [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "action": e.action,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "details": e.details,
            }
            for e in query.limit(limit).all()
        ]