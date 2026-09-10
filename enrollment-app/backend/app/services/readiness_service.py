"""ReadinessService — Phase 5 (T029–T033, contracts/photo-quality.md).

Hard MVP readiness rule (user-approved Phase 5 instruction):

    approved_suitable_count = count of EXACT-DUPLICATE-DEDUPED photos where
                              quality_status == SUITABLE AND approved == true

    < 5  → NOT_READY
    >= 5 → READY

- Only SUITABLE AND approved photos count. UNSUITABLE, REVIEW_REQUIRED, PENDING,
  and unapproved photos never count.
- Exact duplicates (same `duplicate_group`, i.e. same SHA-256 of the uploaded
  bytes) contribute at most ONE readiness credit — uploading the same photo five
  times can never produce READY (user rule #15).
- `READY` means "the local enrollment manager has a sufficient explicitly approved
  photo set" — NOTHING more. It never triggers enrollment, embeddings, identity
  creation, or any Frigate/HA/MQTT action (user rule #9, FR-022/SC-006).
- `READINESS_CHANGED` audit events are written ONLY when the person's effective
  readiness status actually transitions (e.g. NOT_READY → READY); approving a
  second photo while still NOT_READY emits no misleading transition (rule #13).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings
from app.exceptions import PersonNotFoundError
from app.models.audit import AuditLogEntry
from app.models.enums import AuditAction, EnrollmentStatus, QualityStatus
from app.models.person import Person
from app.models.photo import EnrollmentPhoto
from app.services.audit_service import AuditService

# Status string for the case where no photos exist yet (data-model.md).
DRAFT_STATUS = EnrollmentStatus.DRAFT.value


@dataclass(frozen=True)
class ReadinessCounts:
    """Objective counts feeding the readiness decision (never paths, never bytes)."""

    total_uploaded: int
    suitable_count: int  # quality SUITABLE, regardless of approval
    approved_count: int  # approved regardless of quality
    approved_suitable_count: int  # SUITABLE AND approved, deduped by duplicate_group
    review_required_count: int
    unsuitable_count: int
    pending_count: int
    approved_near_duplicate: bool  # advisory only: approved set contains visual near-duplicates


class ReadinessService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        """``settings`` is only needed for the status/readiness/sync paths (the
        minimum-photo threshold); ``counts()`` works with just a session."""
        self._session = session
        self._settings = settings
        self._audit = AuditService(session)

    # ---- counting -------------------------------------------------------------

    def counts(self, person_id: str) -> ReadinessCounts:
        rows = (
            self._session.query(EnrollmentPhoto)
            .filter(EnrollmentPhoto.person_id == person_id)
            .all()
        )
        suitable = approved = approved_suitable = review = unsuitable = pending = 0
        approved_groups: set[str] = set()
        for r in rows:
            if r.quality_status == QualityStatus.SUITABLE.value:
                suitable += 1
            if r.approved:
                approved += 1
            if r.quality_status == QualityStatus.REVIEW_REQUIRED.value:
                review += 1
            elif r.quality_status == QualityStatus.UNSUITABLE.value:
                unsuitable += 1
            elif r.quality_status in (QualityStatus.PENDING.value, None):
                pending += 1
            if not (r.approved and r.quality_status == QualityStatus.SUITABLE.value):
                continue
            if r.duplicate_group is None:
                # Legacy/unknown group: each such photo is its own credit.
                approved_suitable += 1
            elif r.duplicate_group not in approved_groups:
                # One credit per exact-duplicate group (user rule #15).
                approved_groups.add(r.duplicate_group)
                approved_suitable += 1
        # Phase 5 advisory (never blocking): has any APPROVED photo been flagged as
        # a near-duplicate of another same-person photo? Purely informational — the
        # hard gate stays approved_suitable_count (user's Phase 5 rules #16/#18).
        approved_near_duplicate = any(
            isinstance(r.approved and (r.measurements or {}).get("near_duplicate_advisory"), dict)
            for r in rows
        )
        return ReadinessCounts(
            total_uploaded=len(rows),
            suitable_count=suitable,
            approved_count=approved,
            approved_suitable_count=approved_suitable,
            review_required_count=review,
            unsuitable_count=unsuitable,
            pending_count=pending,
            approved_near_duplicate=approved_near_duplicate,
        )

    def status_for(self, counts: ReadinessCounts) -> str:
        if self._settings is None:  # pragma: no cover — defensive
            raise RuntimeError("ReadinessService requires settings for status computation")
        minimum = self._settings.quality.min_approved_suitable
        if counts.total_uploaded == 0:
            return DRAFT_STATUS
        return (
            EnrollmentStatus.READY.value
            if counts.approved_suitable_count >= minimum
            else EnrollmentStatus.NOT_READY.value
        )

    # ---- response --------------------------------------------------------------

    def readiness(self, person_id: str) -> dict:
        person = self._session.get(Person, person_id)
        if person is None:
            raise PersonNotFoundError(f"Person {person_id} not found")
        counts = self.counts(person_id)
        assert self._settings is not None  # endpoint always injects settings
        minimum = self._settings.quality.min_approved_suitable
        status = self.status_for(counts)
        remaining = max(0, minimum - counts.approved_suitable_count)
        return {
            "person_id": person_id,
            "status": status,
            "minimum_required": minimum,
            "required_min": minimum,  # contract alias (rest-api.md)
            "approved_suitable_count": counts.approved_suitable_count,
            "suitable_count": counts.suitable_count,  # total SUITABLE, regardless of approval
            "remaining_required": remaining,
            "total_uploaded": counts.total_uploaded,
            "approved_count": counts.approved_count,
            "review_required_count": counts.review_required_count,
            "unsuitable_count": counts.unsuitable_count,
            "pending_count": counts.pending_count,
            "enrollment_enabled": False,  # Phase 6 is blocked; READY ≠ ENROLLED
            "near_duplicate_advisory": counts.approved_near_duplicate,
            "missing": [] if remaining == 0 else [f"{remaining} more approved suitable photo(s)"],
            "diversity": {
                "has_multiple_angles": None,
                "has_expression_variation": None,
                "notes": "Diversity tags are advisory user metadata; not a readiness criterion.",
            },
        }

    # ---- sync + audit ------------------------------------------------------------

    def sync_person_status(self, person_id: str) -> str:
        """Recompute the person's effective readiness status, persist it on the
        Person row, and audit READINESS_CHANGED ONLY on an actual transition.

        Returns the resulting status string. Call after any photo mutation that
        can change readiness (upload, approve, unapprove, delete, reanalysis).
        """
        person = self._session.get(Person, person_id)
        if person is None:
            raise PersonNotFoundError(f"Person {person_id} not found")
        assert self._settings is not None  # sync path always has settings
        counts = self.counts(person_id)
        new_status = self.status_for(counts)
        old_status = person.enrollment_status
        if new_status != old_status:
            person.enrollment_status = new_status
            self._audit.record(
                AuditAction.READINESS_CHANGED,
                entity_type="person",
                entity_id=person_id,
                details={
                    "from": old_status,
                    "to": new_status,
                    "approved_suitable_count": counts.approved_suitable_count,
                },
            )
            self._session.commit()
        return new_status

    # ---- audit read (reuse PersonService's list but keep service lean) ---------

    def audit_entries(self, person_id: str | None = None, limit: int = 200) -> list[dict]:
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