"""EnrollmentService — Phase 6 enrollment orchestrator (Feature 002).

Coordinates the app-side enrollment transaction on top of the real Phase 1–5 models
and services and the single Frigate boundary (``FrigateEnrollmentService``). It never
talks HTTP directly and never bypasses the feature flag.

Hard invariants:
  - FRIGATE_ENROLLMENT_ENABLED must be true; otherwise every mutating operation raises
    the canonical FeatureNotEnabledError and performs ZERO Frigate calls.
  - ``frigate_identity_name`` is persisted ONLY after external verification succeeds.
  - Photos are marked ``enrolled_in_frigate`` ONLY after external verification.
  - Partial Frigate mutation on failure is rolled back (delete the created identity);
    if rollback also fails, local state goes to ERROR and RECONCILIATION_REQUIRED is
    surfaced — evidence is preserved, never silently cleared.
  - A per-person guard prevents concurrent double enrollment in this single process.
  - reconcile() is strictly read-only.

Audit uses the existing AuditService/AuditAction. Details carry only metadata
(person UUID, photo UUIDs, outcome, sanitized identity name) — never bytes/secrets/paths.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.exceptions import (
    EnrollmentInProgressError,
    EnrollmentNotReadyError,
    FeatureNotEnabledError,
    FrigateEnrollmentError,
    IdentityConflictError,
    PersonNotFoundError,
    ReconciliationRequiredError,
)
from app.models.enums import AuditAction, EnrollmentStatus, QualityStatus
from app.models.person import Person
from app.models.photo import EnrollmentPhoto
from app.services.audit_service import AuditService
from app.services.frigate_service import (
    FrigateEnrollmentService,
    _sanitize_create_name,
    is_valid_frigate_identity_name,
)
from app.services.photo_service import PhotoService
from app.services.readiness_service import ReadinessService

_LOG = logging.getLogger(__name__)

# Per-person concurrency guard for this single-process app. A person-scoped lock is
# acquired non-blocking; a second concurrent caller for the SAME person is rejected.
# Different persons are not globally serialized.
_GUARD_REGISTRY_LOCK = threading.Lock()
_PERSON_LOCKS: dict[str, threading.Lock] = {}


def _person_lock(person_id: str) -> threading.Lock:
    with _GUARD_REGISTRY_LOCK:
        lock = _PERSON_LOCKS.get(person_id)
        if lock is None:
            lock = threading.Lock()
            _PERSON_LOCKS[person_id] = lock
        return lock


@dataclass(frozen=True)
class SelectedPhoto:
    """A photo chosen for enrollment (one per exact-duplicate group)."""

    id: str
    duplicate_group: str | None


class EnrollmentService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        frigate: FrigateEnrollmentService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._audit = AuditService(session)
        self._readiness = ReadinessService(session, settings)
        self._photos = PhotoService(session, settings)
        # Default boundary has no transport; production wires a real one, tests inject
        # a fake. The boundary itself also enforces the feature flag (defense in depth).
        self._frigate = frigate or FrigateEnrollmentService(settings, transport=None)

    # ---- feature gate ----------------------------------------------------------

    def _require_enabled(self, operation: str) -> None:
        if not self._settings.frigate_enrollment_enabled:
            raise FeatureNotEnabledError(
                f"Frigate enrollment is disabled (FRIGATE_ENROLLMENT_ENABLED=false); "
                f"'{operation}' performs no Frigate mutation.",
            )

    # ---- helpers ---------------------------------------------------------------

    def _get_person(self, person_id: str) -> Person:
        person = self._session.get(Person, person_id)
        if person is None:
            raise PersonNotFoundError(f"Person {person_id} not found")
        return person

    def _select_photos(self, person_id: str) -> list[SelectedPhoto]:
        """SUITABLE AND approved, deduplicated by exact duplicate_group (one per group;
        legacy null group counts as unique). Near-duplicate advisory never removes a
        photo. Ordered by created_at for determinism."""
        rows = (
            self._session.query(EnrollmentPhoto)
            .filter(EnrollmentPhoto.person_id == person_id)
            .order_by(EnrollmentPhoto.created_at)
            .all()
        )
        selected: list[SelectedPhoto] = []
        seen_groups: set[str] = set()
        for r in rows:
            if not (r.approved and r.quality_status == QualityStatus.SUITABLE.value):
                continue
            if r.duplicate_group is not None:
                if r.duplicate_group in seen_groups:
                    continue
                seen_groups.add(r.duplicate_group)
            selected.append(SelectedPhoto(id=r.id, duplicate_group=r.duplicate_group))
        return selected

    def _local_candidate_name(self, person: Person) -> str:
        """Derive a safe candidate Frigate identity name from the display name only,
        deduplicated against **LOCAL application reservations only** (other persons'
        ``frigate_identity_name``). Automatic ``_2/_3`` suffixing is allowed HERE —
        this happens BEFORE any live Frigate inspection.

        This must NOT consult live ``/api/faces``: a collision with unexpected external
        biometric state is a safety event to investigate (IDENTITY_CONFLICT /
        RECONCILIATION_REQUIRED), never something to bypass with another suffix.
        """
        local_taken = self._local_identity_names(exclude_person_id=person.id)
        base = _sanitize_create_name(person.display_name)
        if not is_valid_frigate_identity_name(base):
            base = "person"
        candidate = base
        suffix = 1
        while candidate in local_taken or not is_valid_frigate_identity_name(candidate):
            suffix += 1
            tail = f"_{suffix}"
            candidate = f"{base[: max(1, 50 - len(tail))]}{tail}"
            if suffix > 9999:  # pragma: no cover — defensive
                raise IdentityConflictError(
                    "Could not derive a unique local Frigate identity candidate."
                )
        return candidate

    def _local_identity_names(self, exclude_person_id: str | None = None) -> set[str]:
        q = self._session.query(Person.frigate_identity_name).filter(
            Person.frigate_identity_name.isnot(None)
        )
        names = {n for (n,) in q.all() if n}
        if exclude_person_id is not None:
            person = self._session.get(Person, exclude_person_id)
            if person and person.frigate_identity_name:
                names.discard(person.frigate_identity_name)
        return names

    # ---- enroll ----------------------------------------------------------------

    def enroll(self, person_id: str) -> dict[str, Any]:
        """Enroll a READY, enabled person. See module docstring for the invariants."""
        self._require_enabled("enroll")

        lock = _person_lock(person_id)
        if not lock.acquire(blocking=False):
            raise EnrollmentInProgressError(
                f"An enrollment/removal for person {person_id} is already in progress."
            )
        try:
            return self._enroll_locked(person_id)
        finally:
            lock.release()

    def _enroll_locked(self, person_id: str) -> dict[str, Any]:
        # (2) re-read person/readiness inside the operation
        person = self._get_person(person_id)

        # (4) preconditions — ZERO Frigate mutation if any fail
        if not person.enabled:
            raise EnrollmentNotReadyError("Disabled people cannot be enrolled.")
        counts = self._readiness.counts(person_id)
        status = self._readiness.status_for(counts)
        if status != EnrollmentStatus.READY.value:
            raise EnrollmentNotReadyError(
                f"Person is not READY (status={status}, "
                f"approved_suitable_count={counts.approved_suitable_count})."
            )
        selected = self._select_photos(person_id)
        minimum = self._settings.quality.min_approved_suitable
        if len(selected) < minimum:
            raise EnrollmentNotReadyError(
                f"Only {len(selected)} distinct approved suitable photos "
                f"(minimum {minimum})."
            )

        # Choose the candidate against LOCAL reservations only (suffixing allowed here).
        identity_name = self._local_candidate_name(person)

        # (5) inspect live Frigate; (6) STOP on any live collision — never auto-suffix
        # past unexpected external biometric state.
        existing = self._frigate.list_identities()  # may raise FrigateUnavailable/Auth
        if identity_name in existing:
            # A live identity already uses this name and this person is not currently
            # its linked, ENROLLED owner. Do NOT generate another suffix and do NOT
            # append. Classify: if it matches this person's own lingering reference
            # (local drift), require reconciliation; otherwise it's a foreign identity.
            if (
                person.frigate_identity_name == identity_name
                and person.enrollment_status != EnrollmentStatus.ENROLLED.value
            ):
                raise ReconciliationRequiredError(
                    f"Frigate identity '{identity_name}' exists and matches this "
                    f"person's unresolved reference (status={person.enrollment_status}); "
                    f"reconcile before enrolling.",
                    details={"identity": identity_name},
                )
            raise IdentityConflictError(
                f"Frigate identity '{identity_name}' already exists; enrollment stopped "
                f"to avoid creating a duplicate identity.",
                details={"identity": identity_name},
            )

        # (7) local ENROLLING + (8) audit ENROLLMENT_STARTED
        person.enrollment_status = EnrollmentStatus.ENROLLING.value
        self._audit.record(
            AuditAction.ENROLLMENT_STARTED,
            entity_type="person",
            entity_id=person_id,
            details={"identity": identity_name, "photo_ids": [p.id for p in selected]},
        )
        self._session.flush()

        created = False
        submitted_ids: list[str] = []
        try:
            # (9) create identity
            self._frigate.create_identity(identity_name)
            created = True
            # (10) register each selected image once (full original bytes)
            for sel in selected:
                data, _mime = self._photos.get_original_bytes(person_id, sel.id)
                self._frigate.register_face(identity_name, data, filename=f"{sel.id}.jpg")
                submitted_ids.append(sel.id)
                self._audit.record(
                    AuditAction.ENROLLMENT_PHOTO_SUBMITTED,
                    entity_type="photo",
                    entity_id=sel.id,
                    details={"identity": identity_name},
                )
            # (11) verify identity exists + (12) verify accepted crop count — via bounded
            # read-only polling (Frigate is eventually consistent after register_face's
            # async recognizer.clear() rebuild + crop-dir settle). Poll only reads.
            if not self._frigate.wait_for_identity_present(
                identity_name, min_faces=len(submitted_ids)
            ):
                after = self._frigate.list_identities()
                observed = len(after.get(identity_name, []))
                raise FrigateEnrollmentError(
                    f"Frigate identity '{identity_name}' did not reach the expected "
                    f"{len(submitted_ids)} registered face record(s) within the "
                    f"verification timeout (observed {observed}).",
                    details={"identity": identity_name},
                )
        except Exception as exc:
            # Failure path. If nothing external was created, this is a pre-mutation
            # failure; otherwise roll back the partial external state.
            self._handle_enroll_failure(person, identity_name, created, exc)
            raise

        # (13) persist ONLY after verification
        person.frigate_identity_name = identity_name
        for sel in selected:
            row = self._session.get(EnrollmentPhoto, sel.id)
            if row is not None:
                row.enrolled_in_frigate = True
        person.enrollment_status = EnrollmentStatus.ENROLLED.value
        # (14) audit ENROLLMENT_COMPLETED
        self._audit.record(
            AuditAction.ENROLLMENT_COMPLETED,
            entity_type="person",
            entity_id=person_id,
            details={
                "identity": identity_name,
                "enrolled_photo_ids": submitted_ids,
                "count": len(submitted_ids),
            },
        )
        # (15) commit
        self._session.commit()
        return self._result(person)

    def _handle_enroll_failure(
        self,
        person: Person,
        identity_name: str,
        created: bool,
        exc: Exception,
    ) -> None:
        person_id = person.id
        if not created:
            # (7) pre-mutation failure: nothing external, return person to READY.
            person.enrollment_status = EnrollmentStatus.READY.value
            self._audit.record(
                AuditAction.ENROLLMENT_FAILED,
                entity_type="person",
                entity_id=person_id,
                details={"identity": identity_name, "phase": "pre_mutation", "reason": str(exc)[:200]},
            )
            self._session.commit()
            return

        # (8) partial failure -> attempt rollback of the external identity.
        self._audit.record(
            AuditAction.ENROLLMENT_FAILED,
            entity_type="person",
            entity_id=person_id,
            details={"identity": identity_name, "phase": "post_mutation", "reason": str(exc)[:200]},
        )
        self._audit.record(
            AuditAction.ENROLLMENT_ROLLBACK_STARTED,
            entity_type="person",
            entity_id=person_id,
            details={"identity": identity_name},
        )
        try:
            # inspect current external identity + enumerate ids, then delete all.
            current = self._frigate.list_identities()
            ids = list(current.get(identity_name, []))
            self._frigate.remove_identity(identity_name, ids)
            # Confirm absence via bounded read-only polling — NEVER declare rollback
            # complete on an immediate read (Frigate delete is eventually consistent).
            if not self._frigate.wait_for_identity_absent(identity_name):
                raise FrigateEnrollmentError(
                    f"Rollback delete issued but identity '{identity_name}' remained "
                    f"present within the verification timeout."
                )
        except Exception as rb_exc:
            # Rollback failed. Persist a DURABLE, sanitized reference to the external
            # identity that may still exist so reconciliation/removal knows exactly what
            # to inspect. Option A: we reuse ``frigate_identity_name`` for this reference,
            # but ONLY together with status == ERROR.
            #
            # IMPORTANT SEMANTICS: frigate_identity_name in ERROR state means
            # "known UNRESOLVED external identity reference" — it does NOT imply a
            # successful enrollment. enrolled_in_frigate flags stay false (they were
            # never set on the failure path), reflecting only what is actually known.
            # A retry cannot blindly recreate/register: the next enroll() re-inspects
            # /api/faces and, finding this same reference live, raises
            # RECONCILIATION_REQUIRED rather than creating a duplicate identity.
            person.frigate_identity_name = identity_name
            person.enrollment_status = EnrollmentStatus.ERROR.value
            self._audit.record(
                AuditAction.ENROLLMENT_ROLLBACK_FAILED,
                entity_type="person",
                entity_id=person_id,
                details={
                    "identity": identity_name,
                    "reason": str(rb_exc)[:200],
                    "unresolved_external_reference": True,
                    "implies_enrolled": False,
                },
            )
            self._session.commit()
            raise ReconciliationRequiredError(
                f"Enrollment failed and rollback could not remove Frigate identity "
                f"'{identity_name}'; a durable unresolved external reference is retained "
                f"for reconciliation. This does NOT mean the person is enrolled.",
                details={"identity": identity_name},
            ) from rb_exc

        # Rollback success: clean local state, return to READY.
        person.frigate_identity_name = None
        person.enrollment_status = EnrollmentStatus.READY.value
        self._audit.record(
            AuditAction.ENROLLMENT_ROLLBACK_COMPLETED,
            entity_type="person",
            entity_id=person_id,
            details={"identity": identity_name},
        )
        self._session.commit()

    # ---- remove enrollment -----------------------------------------------------

    def remove_enrollment(self, person_id: str) -> dict[str, Any]:
        self._require_enabled("remove_enrollment")
        lock = _person_lock(person_id)
        if not lock.acquire(blocking=False):
            raise EnrollmentInProgressError(
                f"An enrollment/removal for person {person_id} is already in progress."
            )
        try:
            return self._remove_locked(person_id)
        finally:
            lock.release()

    def _remove_locked(self, person_id: str) -> dict[str, Any]:
        person = self._get_person(person_id)
        identity_name = person.frigate_identity_name
        if not identity_name:
            raise EnrollmentNotReadyError("Person has no Frigate enrollment to remove.")

        self._audit.record(
            AuditAction.ENROLLMENT_REMOVAL_STARTED,
            entity_type="person",
            entity_id=person_id,
            details={"identity": identity_name},
        )
        self._session.flush()

        # (1) inspect live identity
        current = self._frigate.list_identities()
        if identity_name not in current:
            # External identity already absent.
            if person.enrollment_status == EnrollmentStatus.ERROR.value:
                # ERROR-state cleanup: the durable unresolved reference points at an
                # identity that is confirmed absent externally. This is the desired
                # end-state — finalize local cleanup (never marks ENROLLED, never mutates
                # Frigate). Explicit, feature-gated user action.
                return self._finalize_removal(person, identity_name, external_absent=True)
            # Local says ENROLLED but external is gone → genuine drift; do not guess.
            raise ReconciliationRequiredError(
                f"Frigate identity '{identity_name}' is missing; local state says "
                f"enrolled. Manual reconciliation required.",
                details={"identity": identity_name},
            )
        # (2) enumerate ids, (3) delete all, (4) verify absent (bounded read-only poll)
        ids = list(current.get(identity_name, []))
        try:
            self._frigate.remove_identity(identity_name, ids)
            if not self._frigate.wait_for_identity_absent(identity_name):
                raise FrigateEnrollmentError(
                    f"Frigate identity '{identity_name}' still present after deletion "
                    f"(did not settle within the verification timeout)."
                )
        except FrigateEnrollmentError:
            # External deletion failed → retain everything, do not report success.
            raise
        # (5) only then clear local state + recompute readiness
        return self._finalize_removal(person, identity_name, external_absent=False)

    def _finalize_removal(
        self, person: Person, identity_name: str, *, external_absent: bool
    ) -> dict[str, Any]:
        """Confirmed external absence → clear local enrollment state, recompute
        readiness, audit. Never marks ENROLLED. Never mutates Frigate."""
        person_id = person.id
        for row in (
            self._session.query(EnrollmentPhoto)
            .filter(EnrollmentPhoto.person_id == person_id)
            .all()
        ):
            row.enrolled_in_frigate = False
        person.frigate_identity_name = None
        counts = self._readiness.counts(person_id)
        person.enrollment_status = self._readiness.status_for(counts)
        # (6) audit ENROLLMENT_REMOVED
        self._audit.record(
            AuditAction.ENROLLMENT_REMOVED,
            entity_type="person",
            entity_id=person_id,
            details={
                "identity": identity_name,
                "resulting_status": person.enrollment_status,
                "external_already_absent": external_absent,
            },
        )
        self._session.commit()
        return self._result(person)

    # ---- reconcile (read-only) -------------------------------------------------

    def reconcile(self, person_id: str) -> dict[str, Any]:
        """Read-only comparison of local vs external state. Never mutates anything."""
        person = self._get_person(person_id)
        identities = self._frigate.list_identities()
        identity_name = person.frigate_identity_name
        enrolled_locally = person.enrollment_status == EnrollmentStatus.ENROLLED.value

        self._audit.record(
            AuditAction.RECONCILIATION_RUN,
            entity_type="person",
            entity_id=person_id,
            details={"identity": identity_name, "local_status": person.enrollment_status},
        )
        self._session.commit()

        if enrolled_locally and identity_name:
            if identity_name in identities:
                return self._reconcile_result(person, "CONSISTENT")
            return self._reconcile_result(person, "RECONCILIATION_REQUIRED",
                                          reason="local ENROLLED but external identity missing")

        # ERROR with a durable unresolved external reference (rollback-failure state).
        # frigate_identity_name here is an UNRESOLVED reference, never proof of enrollment.
        if person.enrollment_status == EnrollmentStatus.ERROR.value and identity_name:
            if identity_name in identities:
                return self._reconcile_result(
                    person, "RECONCILIATION_REQUIRED",
                    reason="local ERROR with unresolved external identity that still exists",
                )
            # External residue absent — report it, but NEVER silently mark ENROLLED and
            # never mutate here. Removal/operator action resolves the local ERROR state.
            return self._reconcile_result(
                person, "RECONCILIATION_REQUIRED",
                reason="local ERROR unresolved reference but external identity absent",
            )

        # Local not enrolled: does a matching external identity exist?
        candidate = identity_name or _sanitize_create_name(person.display_name)
        if candidate in identities:
            return self._reconcile_result(person, "IDENTITY_CONFLICT",
                                          reason="external identity exists for a non-enrolled person")
        # Unrelated external identities are ignored.
        return self._reconcile_result(person, "CONSISTENT")

    # ---- result shaping --------------------------------------------------------

    def _result(self, person: Person) -> dict[str, Any]:
        return {
            "person_id": person.id,
            "enrollment_status": person.enrollment_status,
            "frigate_identity_name": person.frigate_identity_name,
        }

    def _reconcile_result(self, person: Person, state: str, *, reason: str | None = None) -> dict[str, Any]:
        return {
            "person_id": person.id,
            "enrollment_status": person.enrollment_status,
            "frigate_identity_name": person.frigate_identity_name,
            "reconciliation_state": state,
            "reason": reason,
        }
