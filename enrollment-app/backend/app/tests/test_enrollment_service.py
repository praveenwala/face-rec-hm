"""Phase 6 EnrollmentService tests (Feature 002) — fully offline.

A controllable FAKE Frigate transport stands in for the real Frigate 0.17.2 HTTP API.
No real HTTP is issued and no real Frigate face library is touched. The fake's response
shapes match the verified 0.17.2 contract
(specs/002/contracts/frigate-0.17.2-api-verification.md):

    GET  /api/faces               -> 200 {name: [filenames]}
    POST /api/faces/{name}/create -> 200 {"success": false, "message": ...}   (folder made)
    POST /api/faces/{name}/register (multipart file) -> 200 {"success": true, ...}
    POST /api/faces/{name}/delete {"ids":[...]} -> 200 {"success": true, ...}

Covered: feature gate, preconditions, success transaction, each failure boundary,
rollback success/failure, existing-identity conflict, remove enrollment, reconciliation,
and per-person concurrency.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

import pytest

from app.config import FrigateConfig, Settings
from app.db import make_session_factory
from app.exceptions import (
    EnrollmentInProgressError,
    EnrollmentNotReadyError,
    FeatureNotEnabledError,
    FrigateAuthError,
    FrigateEnrollmentError,
    FrigateUnavailableError,
    IdentityConflictError,
    ReconciliationRequiredError,
)
from app.models.enums import AuditAction, EnrollmentStatus, QualityStatus
from app.models.audit import AuditLogEntry
from app.models.person import Person
from app.models.photo import EnrollmentPhoto
from app.services.enrollment_service import EnrollmentService
from app.services.frigate_service import FrigateEnrollmentService, PollConfig
from app.services.storage_service import StorageService


# ---------------------------------------------------------------------------
# Fake Frigate transport (matches verified 0.17.2 response shapes)
# ---------------------------------------------------------------------------


class FakeFrigateTransport:
    """In-memory Frigate face library with a call log. Fully controllable failures.

    ``fail_on`` maps a "METHOD /path-prefix" trigger to an exception/behavior:
      - an Exception instance -> raised (mapped by the service)
      - ('http', status, body) -> returned as an error HTTP response
    ``fail_after_registers`` optionally raises after N successful registers.
    """

    def __init__(self) -> None:
        self.library: dict[str, list[str]] = {}
        self.calls: list[tuple[str, str]] = []
        self.mutating_calls: list[tuple[str, str]] = []
        self.fail_on: dict[str, object] = {}
        self.register_count = 0
        self.fail_after_registers: int | None = None
        self.suppress_register_persist = False  # simulate accepted-but-not-stored
        # Eventual-consistency simulation for GET /api/faces (reads only).
        self.get_faces_count = 0
        # ``faces_view(count, library) -> dict`` overrides what a GET observes, so tests
        # can hide/reveal an identity or ramp a face count across successive polls.
        self.faces_view = None

    def _maybe_fail(self, key: str):
        if key in self.fail_on:
            trigger = self.fail_on[key]
            if isinstance(trigger, Exception):
                raise trigger
            if isinstance(trigger, tuple) and trigger and trigger[0] == "http":
                return ("http", trigger[1], trigger[2])
        return None

    def request(self, method, path, *, json=None, files=None):
        self.calls.append((method, path))
        is_mutating = method in ("POST", "PUT", "DELETE")
        if is_mutating:
            self.mutating_calls.append((method, path))

        key = f"{method} {path}"
        # Allow prefix-based triggers too (e.g. "POST /api/faces/x/register").
        forced = self._maybe_fail(key)
        if forced is not None:
            return (forced[1], forced[2])

        if method == "GET" and path == "/api/faces":
            self.get_faces_count += 1
            actual = {k: list(v) for k, v in self.library.items()}
            if self.faces_view is not None:
                return (200, self.faces_view(self.get_faces_count, actual))
            return (200, actual)

        if method == "POST" and path.endswith("/create"):
            name = path.split("/api/faces/")[1].rsplit("/create", 1)[0]
            self.library.setdefault(name, [])
            return (200, {"success": False, "message": "Successfully created face folder."})

        if method == "POST" and path.endswith("/register"):
            name = path.split("/api/faces/")[1].rsplit("/register", 1)[0]
            self.register_count += 1
            if self.fail_after_registers is not None and self.register_count > self.fail_after_registers:
                return (200, {"success": False, "message": "No face was detected."})
            if not self.suppress_register_persist:
                self.library.setdefault(name, []).append(
                    f"{name}_{self.register_count}.webp"
                )
            return (200, {"success": True, "message": "Successfully registered face."})

        if method == "POST" and path.endswith("/delete"):
            name = path.split("/api/faces/")[1].rsplit("/delete", 1)[0]
            ids = (json or {}).get("ids", [])
            if name in self.library:
                self.library[name] = [f for f in self.library[name] if f not in ids]
                if not self.library[name]:
                    del self.library[name]
            return (200, {"success": True, "message": "Successfully deleted faces."})

        return (200, {"success": True})


def _enabled_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        frigate=FrigateConfig(enrollment_enabled=True, api_url="http://127.0.0.1:5001"),
    )


def _disabled_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        frigate=FrigateConfig(enrollment_enabled=False),
    )


def _session_for(settings: Settings):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.people_root.mkdir(parents=True, exist_ok=True)
    factory = make_session_factory(settings.db_path)
    return factory()


def _make_person(session, *, enabled=True, status=EnrollmentStatus.READY.value,
                 display_name="Test Person") -> Person:
    person = Person(
        id=str(uuid.uuid4()),
        display_name=display_name,
        relationship="Family",
        enabled=enabled,
        enrollment_status=status,
    )
    session.add(person)
    session.flush()
    return person


def _add_photo(session, settings, person_id, *, approved=True,
               quality=QualityStatus.SUITABLE.value, dup_group=None, name=None) -> str:
    """Insert a photo row and write a real (tiny) original file so get_original_bytes works."""
    storage = StorageService(settings)
    original_name = name or f"{uuid.uuid4().hex}.jpg"
    data = b"\xff\xd8\xff\xe0" + original_name.encode()  # unique tiny bytes per photo
    path = storage.write_original(person_id, original_name, data)
    rel = str(path.relative_to(settings.data_dir))
    photo = EnrollmentPhoto(
        id=str(uuid.uuid4()),
        person_id=person_id,
        original_filename=original_name,
        stored_filename=path.name,
        storage_path=rel,
        mime_type="image/jpeg",
        file_size=len(data),
        quality_status=quality,
        approved=approved,
        enrolled_in_frigate=False,
        duplicate_group=dup_group if dup_group is not None else uuid.uuid4().hex,
    )
    session.add(photo)
    session.flush()
    return photo.id


def _ready_person_with_photos(session, settings, *, n_distinct=5, extra_dupe=False,
                              enabled=True) -> Person:
    person = _make_person(session, enabled=enabled)
    for _ in range(n_distinct):
        _add_photo(session, settings, person.id)
    if extra_dupe:
        # a second photo sharing a duplicate_group with an added distinct one
        _add_photo(session, settings, person.id, dup_group="SHARED")
        _add_photo(session, settings, person.id, dup_group="SHARED")
    session.commit()
    return person


def _fast_poll(timeout=1.0, interval=0.05):
    """Deterministic, instant PollConfig for tests: a fake clock advances on each
    sleep so timeouts are reached in a bounded number of iterations with zero real
    waiting."""
    clock = {"t": 0.0}

    def monotonic():
        return clock["t"]

    def sleep(dt):
        clock["t"] += dt

    return PollConfig(
        timeout_seconds=timeout,
        interval_seconds=interval,
        sleep=sleep,
        monotonic=monotonic,
    )


def _service(session, settings, transport):
    frigate = FrigateEnrollmentService(settings, transport=transport, poll=_fast_poll())
    return EnrollmentService(session=session, settings=settings, frigate=frigate)


def _audit_actions(session, person_id):
    return [
        e.action
        for e in session.query(AuditLogEntry)
        .filter(AuditLogEntry.entity_id == person_id)
        .order_by(AuditLogEntry.id)
        .all()
    ]


# ---------------------------------------------------------------------------
# FEATURE GATE
# ---------------------------------------------------------------------------


class TestFeatureGate:
    def test_enroll_disabled_zero_mutation(self, tmp_path):
        settings = _disabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings)
        transport = FakeFrigateTransport()
        svc = _service(session, settings, transport)
        with pytest.raises(FeatureNotEnabledError):
            svc.enroll(person.id)
        assert transport.calls == []
        assert transport.mutating_calls == []
        session.close()

    def test_remove_disabled_zero_mutation(self, tmp_path):
        settings = _disabled_settings(tmp_path)
        session = _session_for(settings)
        person = _make_person(session)
        person.frigate_identity_name = "Test_Person"
        session.commit()
        transport = FakeFrigateTransport()
        svc = _service(session, settings, transport)
        with pytest.raises(FeatureNotEnabledError):
            svc.remove_enrollment(person.id)
        assert transport.calls == []
        session.close()


# ---------------------------------------------------------------------------
# PRECONDITIONS
# ---------------------------------------------------------------------------


class TestPreconditions:
    def test_not_ready_no_mutation(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _make_person(session, status=EnrollmentStatus.NOT_READY.value)
        for _ in range(3):  # only 3 distinct approved suitable → below 5
            _add_photo(session, settings, person.id)
        session.commit()
        transport = FakeFrigateTransport()
        svc = _service(session, settings, transport)
        with pytest.raises(EnrollmentNotReadyError):
            svc.enroll(person.id)
        assert transport.mutating_calls == []
        session.close()

    def test_disabled_person_no_mutation(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings, enabled=False)
        transport = FakeFrigateTransport()
        svc = _service(session, settings, transport)
        with pytest.raises(EnrollmentNotReadyError):
            svc.enroll(person.id)
        assert transport.mutating_calls == []
        session.close()

    def test_insufficient_approved_suitable(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _make_person(session)
        # 4 distinct approved suitable + 1 unapproved + 1 unsuitable → still < 5
        for _ in range(4):
            _add_photo(session, settings, person.id, approved=True)
        _add_photo(session, settings, person.id, approved=False)
        _add_photo(session, settings, person.id, approved=True,
                   quality=QualityStatus.UNSUITABLE.value)
        session.commit()
        transport = FakeFrigateTransport()
        svc = _service(session, settings, transport)
        with pytest.raises(EnrollmentNotReadyError):
            svc.enroll(person.id)
        assert transport.mutating_calls == []
        session.close()

    def test_exact_duplicates_dedupe_selection(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _make_person(session)
        # 5 photos but two share one duplicate_group → only 4 distinct credits → NOT READY
        for _ in range(3):
            _add_photo(session, settings, person.id)
        _add_photo(session, settings, person.id, dup_group="G")
        _add_photo(session, settings, person.id, dup_group="G")
        session.commit()
        transport = FakeFrigateTransport()
        svc = _service(session, settings, transport)
        with pytest.raises(EnrollmentNotReadyError):
            svc.enroll(person.id)
        assert transport.mutating_calls == []
        session.close()


# ---------------------------------------------------------------------------
# SUCCESS
# ---------------------------------------------------------------------------


class TestSuccess:
    def test_success_transaction(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings, n_distinct=6)
        transport = FakeFrigateTransport()
        svc = _service(session, settings, transport)

        result = svc.enroll(person.id)

        # create called exactly once
        creates = [c for c in transport.mutating_calls if c[1].endswith("/create")]
        registers = [c for c in transport.mutating_calls if c[1].endswith("/register")]
        assert len(creates) == 1
        assert len(registers) == 6  # 6 distinct approved suitable photos, once each

        session.refresh(person)
        assert person.enrollment_status == EnrollmentStatus.ENROLLED.value
        assert person.frigate_identity_name  # persisted only after verify
        rows = session.query(EnrollmentPhoto).filter_by(person_id=person.id).all()
        assert all(r.enrolled_in_frigate for r in rows)
        assert result["enrollment_status"] == "ENROLLED"

        actions = _audit_actions(session, person.id)
        assert AuditAction.ENROLLMENT_STARTED.value in actions
        assert AuditAction.ENROLLMENT_COMPLETED.value in actions
        session.close()

    def test_dedupe_registers_one_per_group(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _make_person(session)
        for _ in range(5):
            _add_photo(session, settings, person.id)
        _add_photo(session, settings, person.id, dup_group="DUP")
        _add_photo(session, settings, person.id, dup_group="DUP")  # duplicate, not re-registered
        session.commit()
        transport = FakeFrigateTransport()
        svc = _service(session, settings, transport)
        svc.enroll(person.id)
        registers = [c for c in transport.mutating_calls if c[1].endswith("/register")]
        assert len(registers) == 6  # 5 distinct + 1 for the DUP group (once)
        session.close()


# ---------------------------------------------------------------------------
# FAILURES (pre-mutation)
# ---------------------------------------------------------------------------


class TestPreMutationFailures:
    def test_frigate_unavailable_before_mutation(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings)
        transport = FakeFrigateTransport()
        transport.fail_on["GET /api/faces"] = ConnectionError("down")
        svc = _service(session, settings, transport)
        with pytest.raises(FrigateUnavailableError):
            svc.enroll(person.id)
        assert transport.mutating_calls == []
        session.refresh(person)
        assert person.frigate_identity_name is None
        session.close()

    def test_auth_failure_before_mutation(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings)
        transport = FakeFrigateTransport()
        transport.fail_on["GET /api/faces"] = ("http", 401, {"message": "unauth"})
        svc = _service(session, settings, transport)
        with pytest.raises(FrigateAuthError):
            svc.enroll(person.id)
        assert transport.mutating_calls == []
        session.close()


# ---------------------------------------------------------------------------
# FAILURES with ROLLBACK
# ---------------------------------------------------------------------------


class TestRollback:
    def test_create_failure_is_pre_mutation(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings)
        transport = FakeFrigateTransport()
        # create returns an error before any successful mutation persists
        transport.fail_on["POST /api/faces/Test_Person/create"] = ("http", 500, {"message": "boom"})
        svc = _service(session, settings, transport)
        with pytest.raises(FrigateEnrollmentError):
            svc.enroll(person.id)
        session.refresh(person)
        assert person.frigate_identity_name is None
        assert person.enrollment_status == EnrollmentStatus.READY.value
        session.close()

    def test_middle_register_failure_rolls_back(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings, n_distinct=5)
        transport = FakeFrigateTransport()
        transport.fail_after_registers = 2  # 3rd register reports "No face detected"
        svc = _service(session, settings, transport)
        with pytest.raises(FrigateEnrollmentError):
            svc.enroll(person.id)
        # rollback deleted the identity
        assert transport.library == {}
        session.refresh(person)
        assert person.frigate_identity_name is None
        assert person.enrollment_status == EnrollmentStatus.READY.value
        rows = session.query(EnrollmentPhoto).filter_by(person_id=person.id).all()
        assert all(not r.enrolled_in_frigate for r in rows)
        actions = _audit_actions(session, person.id)
        assert AuditAction.ENROLLMENT_FAILED.value in actions
        assert AuditAction.ENROLLMENT_ROLLBACK_STARTED.value in actions
        assert AuditAction.ENROLLMENT_ROLLBACK_COMPLETED.value in actions
        session.close()

    def test_verify_failure_rolls_back(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings, n_distinct=5)
        transport = FakeFrigateTransport()
        transport.suppress_register_persist = True  # registers "succeed" but nothing stored
        svc = _service(session, settings, transport)
        with pytest.raises(FrigateEnrollmentError):
            svc.enroll(person.id)
        session.refresh(person)
        assert person.frigate_identity_name is None
        assert person.enrollment_status == EnrollmentStatus.READY.value
        session.close()

    def test_rollback_failure_sets_error_and_reconciliation(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings, n_distinct=5)
        transport = FakeFrigateTransport()
        transport.fail_after_registers = 2  # force a post-mutation failure
        # and make the rollback delete fail
        transport.fail_on["POST /api/faces/Test_Person/delete"] = ("http", 500, {"message": "no delete"})
        svc = _service(session, settings, transport)
        with pytest.raises(ReconciliationRequiredError):
            svc.enroll(person.id)
        session.refresh(person)
        assert person.enrollment_status == EnrollmentStatus.ERROR.value
        actions = _audit_actions(session, person.id)
        assert AuditAction.ENROLLMENT_ROLLBACK_FAILED.value in actions
        session.close()


# ---------------------------------------------------------------------------
# CONFLICT
# ---------------------------------------------------------------------------


class TestConflict:
    def test_live_external_identity_collision_stops(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings)
        transport = FakeFrigateTransport()
        # the candidate name derived from "Test Person" is "Test_Person"
        transport.library["Test_Person"] = ["Test_Person_1.webp"]
        svc = _service(session, settings, transport)
        with pytest.raises(IdentityConflictError):
            svc.enroll(person.id)
        # STOP: no create/register, no second candidate, external identity untouched.
        assert transport.mutating_calls == []
        assert list(transport.library.keys()) == ["Test_Person"]
        assert "Test_Person_2" not in transport.library
        session.refresh(person)
        assert person.frigate_identity_name is None
        session.close()

    def test_local_only_collision_suffixes_before_live(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        # Another LOCAL person already reserves "Test_Person" locally, but Frigate is
        # empty. Local suffixing may deterministically pick Test_Person_2 before any
        # live inspection, and enrollment proceeds.
        other = _make_person(session, display_name="Other")
        other.frigate_identity_name = "Test_Person"
        other.enrollment_status = EnrollmentStatus.ENROLLED.value
        session.commit()
        person = _ready_person_with_photos(session, settings)  # display_name "Test Person"
        transport = FakeFrigateTransport()  # empty live library
        svc = _service(session, settings, transport)
        result = svc.enroll(person.id)
        assert result["frigate_identity_name"] == "Test_Person_2"
        assert "Test_Person_2" in transport.library
        session.close()

    def test_no_fallback_suffix_after_live_collision(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings)
        transport = FakeFrigateTransport()
        # Both the base and the would-be local suffix exist live — must NOT try _3.
        transport.library["Test_Person"] = ["Test_Person_1.webp"]
        svc = _service(session, settings, transport)
        with pytest.raises(IdentityConflictError):
            svc.enroll(person.id)
        assert transport.mutating_calls == []
        assert "Test_Person_2" not in transport.library
        assert "Test_Person_3" not in transport.library
        session.close()


# ---------------------------------------------------------------------------
# REMOVE ENROLLMENT
# ---------------------------------------------------------------------------


class TestRemove:
    def _enroll_first(self, session, settings, transport):
        person = _ready_person_with_photos(session, settings, n_distinct=5)
        svc = _service(session, settings, transport)
        svc.enroll(person.id)
        session.refresh(person)
        return person, svc

    def test_successful_removal(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        transport = FakeFrigateTransport()
        person, svc = self._enroll_first(session, settings, transport)
        name = person.frigate_identity_name
        assert name in transport.library
        result = svc.remove_enrollment(person.id)
        assert name not in transport.library
        session.refresh(person)
        assert person.frigate_identity_name is None
        rows = session.query(EnrollmentPhoto).filter_by(person_id=person.id).all()
        assert all(not r.enrolled_in_frigate for r in rows)
        # 5 approved suitable remain → recomputed READY
        assert person.enrollment_status == EnrollmentStatus.READY.value
        assert AuditAction.ENROLLMENT_REMOVED.value in _audit_actions(session, person.id)
        session.close()

    def test_failed_external_deletion_retains_state(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        transport = FakeFrigateTransport()
        person, svc = self._enroll_first(session, settings, transport)
        name = person.frigate_identity_name
        transport.fail_on[f"POST /api/faces/{name}/delete"] = ("http", 500, {"message": "no"})
        with pytest.raises(FrigateEnrollmentError):
            svc.remove_enrollment(person.id)
        session.refresh(person)
        # retained: identity name kept, photos still enrolled
        assert person.frigate_identity_name == name
        rows = session.query(EnrollmentPhoto).filter_by(person_id=person.id).all()
        assert all(r.enrolled_in_frigate for r in rows)
        assert name in transport.library  # external identity preserved
        session.close()

    def test_remove_when_external_missing_is_reconciliation(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        transport = FakeFrigateTransport()
        person, svc = self._enroll_first(session, settings, transport)
        name = person.frigate_identity_name
        # external identity vanished out of band
        del transport.library[name]
        with pytest.raises(ReconciliationRequiredError):
            svc.remove_enrollment(person.id)
        session.refresh(person)
        # local metadata retained for reconciliation
        assert person.frigate_identity_name == name
        session.close()


# ---------------------------------------------------------------------------
# RECONCILIATION (read-only)
# ---------------------------------------------------------------------------


class TestReconcile:
    def test_consistent(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        transport = FakeFrigateTransport()
        person = _ready_person_with_photos(session, settings, n_distinct=5)
        svc = _service(session, settings, transport)
        svc.enroll(person.id)
        session.refresh(person)
        transport.mutating_calls.clear()
        result = svc.reconcile(person.id)
        assert result["reconciliation_state"] == "CONSISTENT"
        assert transport.mutating_calls == []  # read-only
        session.close()

    def test_external_missing(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        transport = FakeFrigateTransport()
        person = _ready_person_with_photos(session, settings, n_distinct=5)
        svc = _service(session, settings, transport)
        svc.enroll(person.id)
        session.refresh(person)
        del transport.library[person.frigate_identity_name]
        transport.mutating_calls.clear()
        result = svc.reconcile(person.id)
        assert result["reconciliation_state"] == "RECONCILIATION_REQUIRED"
        assert transport.mutating_calls == []
        session.close()

    def test_unexpected_external_identity_for_non_enrolled(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        transport = FakeFrigateTransport()
        person = _make_person(session, display_name="Test Person")
        session.commit()
        transport.library["Test_Person"] = ["Test_Person_1.webp"]
        svc = _service(session, settings, transport)
        result = svc.reconcile(person.id)
        assert result["reconciliation_state"] == "IDENTITY_CONFLICT"
        assert transport.mutating_calls == []
        session.close()

    def test_unrelated_identities_ignored(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        transport = FakeFrigateTransport()
        person = _make_person(session, display_name="Test Person")
        session.commit()
        transport.library["SomebodyElse"] = ["SomebodyElse_1.webp"]
        svc = _service(session, settings, transport)
        result = svc.reconcile(person.id)
        assert result["reconciliation_state"] == "CONSISTENT"
        assert transport.mutating_calls == []
        session.close()


# ---------------------------------------------------------------------------
# CONCURRENCY
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_same_person_second_call_rejected(self, tmp_path):
        from app.services import enrollment_service as es

        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings, n_distinct=5)
        transport = FakeFrigateTransport()
        svc = _service(session, settings, transport)

        # Hold the person lock to simulate an in-flight enrollment, then a second call
        # must be rejected without any duplicate registration.
        lock = es._person_lock(person.id)
        assert lock.acquire(blocking=False)
        try:
            with pytest.raises(EnrollmentInProgressError):
                svc.enroll(person.id)
            assert transport.mutating_calls == []
        finally:
            lock.release()
        session.close()

    def test_guard_released_after_success(self, tmp_path):
        from app.services import enrollment_service as es

        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings, n_distinct=5)
        transport = FakeFrigateTransport()
        svc = _service(session, settings, transport)
        svc.enroll(person.id)
        # lock must be free again after a successful enroll
        lock = es._person_lock(person.id)
        assert lock.acquire(blocking=False)
        lock.release()
        session.close()


# ---------------------------------------------------------------------------
# G6 HARDENING: durable rollback-failure reference, ERROR reconcile & cleanup
# ---------------------------------------------------------------------------


def _force_rollback_failure(session, settings):
    """Enroll into a transport that fails a register (post-mutation) AND fails the
    rollback delete, leaving a durable ERROR + unresolved external reference."""
    person = _ready_person_with_photos(session, settings, n_distinct=5)
    transport = FakeFrigateTransport()
    transport.fail_after_registers = 2  # post-mutation failure
    transport.fail_on["POST /api/faces/Test_Person/delete"] = ("http", 500, {"message": "no delete"})
    svc = _service(session, settings, transport)
    with pytest.raises(ReconciliationRequiredError):
        svc.enroll(person.id)
    session.refresh(person)
    return person, transport


class TestRollbackFailureDurableReference:
    def test_error_state_with_durable_reference(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person, transport = _force_rollback_failure(session, settings)
        # mutation occurred (create + registers)
        assert any(c[1].endswith("/create") for c in transport.mutating_calls)
        assert any(c[1].endswith("/register") for c in transport.mutating_calls)
        # ERROR + durable unresolved external reference retained
        assert person.enrollment_status == EnrollmentStatus.ERROR.value
        assert person.frigate_identity_name == "Test_Person"
        # NOT reported ENROLLED; enrolled flags reflect only known state (false)
        rows = session.query(EnrollmentPhoto).filter_by(person_id=person.id).all()
        assert all(not r.enrolled_in_frigate for r in rows)
        # audit recorded rollback failure with explicit non-enrolled meaning
        entry = (
            session.query(AuditLogEntry)
            .filter(AuditLogEntry.action == AuditAction.ENROLLMENT_ROLLBACK_FAILED.value)
            .order_by(AuditLogEntry.id.desc())
            .first()
        )
        assert entry is not None
        assert entry.details.get("unresolved_external_reference") is True
        assert entry.details.get("implies_enrolled") is False
        session.close()

    def test_retry_from_error_does_not_recreate(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person, transport = _force_rollback_failure(session, settings)
        # The residual external identity still exists in the fake library.
        assert "Test_Person" in transport.library
        # A blind retry must NOT create/register another identity — it must stop.
        transport.mutating_calls.clear()
        svc = _service(session, settings, transport)
        with pytest.raises(ReconciliationRequiredError):
            svc.enroll(person.id)
        assert transport.mutating_calls == []
        session.close()

    def test_reconcile_error_external_exists(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person, transport = _force_rollback_failure(session, settings)
        transport.mutating_calls.clear()
        svc = _service(session, settings, transport)
        result = svc.reconcile(person.id)
        assert result["reconciliation_state"] == "RECONCILIATION_REQUIRED"
        assert result["frigate_identity_name"] == "Test_Person"
        assert transport.mutating_calls == []  # read-only
        # never silently marked ENROLLED
        session.refresh(person)
        assert person.enrollment_status == EnrollmentStatus.ERROR.value
        session.close()

    def test_reconcile_error_external_absent_never_enrolled(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person, transport = _force_rollback_failure(session, settings)
        # external residue vanished out of band
        del transport.library["Test_Person"]
        transport.mutating_calls.clear()
        svc = _service(session, settings, transport)
        result = svc.reconcile(person.id)
        assert result["reconciliation_state"] == "RECONCILIATION_REQUIRED"
        assert transport.mutating_calls == []
        session.refresh(person)
        assert person.enrollment_status == EnrollmentStatus.ERROR.value  # never ENROLLED
        session.close()

    def test_remove_enrollment_from_error_cleans_external(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person, transport = _force_rollback_failure(session, settings)
        assert "Test_Person" in transport.library
        # The delete-failure trigger existed only to force the earlier rollback failure;
        # the operator's environment is now healthy, so clear it for the explicit removal.
        transport.fail_on.pop("POST /api/faces/Test_Person/delete", None)
        svc = _service(session, settings, transport)
        result = svc.remove_enrollment(person.id)
        # external cleaned, reference cleared, readiness restored (5 approved suitable)
        assert "Test_Person" not in transport.library
        session.refresh(person)
        assert person.frigate_identity_name is None
        assert person.enrollment_status == EnrollmentStatus.READY.value
        rows = session.query(EnrollmentPhoto).filter_by(person_id=person.id).all()
        assert all(not r.enrolled_in_frigate for r in rows)
        assert result["enrollment_status"] == EnrollmentStatus.READY.value
        session.close()

    def test_remove_enrollment_from_error_external_already_absent(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person, transport = _force_rollback_failure(session, settings)
        del transport.library["Test_Person"]  # residue already gone
        transport.mutating_calls.clear()
        svc = _service(session, settings, transport)
        result = svc.remove_enrollment(person.id)
        # confirmed absence => finalize cleanup, no Frigate delete issued, never ENROLLED
        assert not any(c[1].endswith("/delete") for c in transport.mutating_calls)
        session.refresh(person)
        assert person.frigate_identity_name is None
        assert person.enrollment_status == EnrollmentStatus.READY.value
        assert result["enrollment_status"] == EnrollmentStatus.READY.value
        session.close()


# ---------------------------------------------------------------------------
# EVENTUAL-CONSISTENCY BUG FIX — bounded polling (tests A–F)
# ---------------------------------------------------------------------------


class TestEventualConsistency:
    """Frigate 0.17.2 register/delete are eventually consistent. The service must poll
    (read-only) until the expected state settles, never decide on a single immediate
    read. Fake clock => instant, deterministic; no real waiting."""

    def test_A_delayed_registration_visibility(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings, n_distinct=6)
        transport = FakeFrigateTransport()

        # GET /api/faces returns {} for the first 2 polls, then reveals the real library.
        def view(n, actual):
            return {} if n <= 2 else actual
        transport.faces_view = view

        svc = _service(session, settings, transport)
        result = svc.enroll(person.id)

        assert result["enrollment_status"] == EnrollmentStatus.ENROLLED.value
        creates = [c for c in transport.mutating_calls if c[1].endswith("/create")]
        registers = [c for c in transport.mutating_calls if c[1].endswith("/register")]
        assert len(creates) == 1
        assert len(registers) == 6  # each selected image once; polling caused NO re-mutation
        session.refresh(person)
        assert person.frigate_identity_name == "Test_Person"
        session.close()

    def test_B_rollback_delete_delayed_disappearance(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings, n_distinct=5)
        transport = FakeFrigateTransport()
        # Force a post-mutation failure so rollback runs.
        transport.fail_after_registers = 2

        # After the identity is deleted from the library, keep SHOWING it for the first
        # 2 post-delete polls, then reflect true (absent) state.
        state = {"deleted": False, "polls_after_delete": 0}
        real_request = transport.request

        def wrapper(method, path, *, json=None, files=None):
            if method == "POST" and path.endswith("/delete"):
                state["deleted"] = True
            return real_request(method, path, json=json, files=files)
        transport.request = wrapper

        def view(n, actual):
            if state["deleted"] and "Test_Person" not in actual:
                state["polls_after_delete"] += 1
                if state["polls_after_delete"] <= 2:
                    return {"Test_Person": ["Test_Person_1.webp"]}  # stale visibility
            return actual
        transport.faces_view = view

        svc = _service(session, settings, transport)
        with pytest.raises(FrigateEnrollmentError):
            svc.enroll(person.id)
        session.refresh(person)
        assert person.enrollment_status == EnrollmentStatus.READY.value
        assert person.frigate_identity_name is None
        actions = _audit_actions(session, person.id)
        assert AuditAction.ENROLLMENT_ROLLBACK_COMPLETED.value in actions
        session.close()

    def test_C_rollback_never_settles(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings, n_distinct=5)
        transport = FakeFrigateTransport()
        transport.fail_after_registers = 2  # post-mutation failure → rollback

        # Delete "succeeds" but the identity NEVER disappears from GET within timeout.
        # Only force stale visibility AFTER the delete is issued, so the pre-enrollment
        # collision check still legitimately sees {}.
        state = {"deleted": False}
        real_request = transport.request

        def wrapper(method, path, *, json=None, files=None):
            if method == "POST" and path.endswith("/delete"):
                state["deleted"] = True
            return real_request(method, path, json=json, files=files)
        transport.request = wrapper

        def view(n, actual):
            if state["deleted"]:
                return {"Test_Person": ["Test_Person_1.webp"]}  # never disappears
            return actual
        transport.faces_view = view

        svc = _service(session, settings, transport)
        with pytest.raises(ReconciliationRequiredError):
            svc.enroll(person.id)
        session.refresh(person)
        assert person.enrollment_status == EnrollmentStatus.ERROR.value
        assert person.frigate_identity_name == "Test_Person"  # durable unresolved ref
        rows = session.query(EnrollmentPhoto).filter_by(person_id=person.id).all()
        assert all(not r.enrolled_in_frigate for r in rows)
        actions = _audit_actions(session, person.id)
        assert AuditAction.ENROLLMENT_ROLLBACK_FAILED.value in actions
        # ROLLBACK_COMPLETED must NOT be emitted when absence was never observed.
        assert AuditAction.ENROLLMENT_ROLLBACK_COMPLETED.value not in actions
        session.close()

    def test_D_registration_never_becomes_visible(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings, n_distinct=5)
        transport = FakeFrigateTransport()

        # Registrations "succeed" but the identity NEVER appears → verify times out →
        # rollback begins. Here the delete does settle (identity removed), so rollback
        # completes and the person returns READY (no blind enrollment success).
        def view(n, actual):
            # Hide Test_Person entirely so present-verify times out.
            return {k: v for k, v in actual.items() if k != "Test_Person"}
        transport.faces_view = view

        svc = _service(session, settings, transport)
        with pytest.raises(FrigateEnrollmentError):
            svc.enroll(person.id)
        session.refresh(person)
        assert person.enrollment_status == EnrollmentStatus.READY.value
        assert person.frigate_identity_name is None
        # No blind ENROLLED
        actions = _audit_actions(session, person.id)
        assert AuditAction.ENROLLMENT_COMPLETED.value not in actions
        session.close()

    def test_E_expected_face_count_delayed(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings, n_distinct=6)
        transport = FakeFrigateTransport()

        # Identity visible but face count ramps 2 -> 4 -> 6 across successive polls.
        ramp = {1: 2, 2: 4}

        def view(n, actual):
            faces = actual.get("Test_Person")
            if not faces:
                return actual
            cap = ramp.get(n)  # for early polls, show fewer than the real count
            if cap is not None:
                clipped = dict(actual)
                clipped["Test_Person"] = faces[:cap]
                return clipped
            return actual
        transport.faces_view = view

        svc = _service(session, settings, transport)
        result = svc.enroll(person.id)
        assert result["enrollment_status"] == EnrollmentStatus.ENROLLED.value
        session.refresh(person)
        assert person.frigate_identity_name == "Test_Person"
        session.close()

    def test_F_no_repeated_mutation_from_polling(self, tmp_path):
        settings = _enabled_settings(tmp_path)
        session = _session_for(settings)
        person = _ready_person_with_photos(session, settings, n_distinct=6)
        transport = FakeFrigateTransport()

        def view(n, actual):
            return {} if n <= 3 else actual  # several empty polls before settling
        transport.faces_view = view

        svc = _service(session, settings, transport)
        svc.enroll(person.id)

        creates = [c for c in transport.mutating_calls if c[1].endswith("/create")]
        registers = [c for c in transport.mutating_calls if c[1].endswith("/register")]
        deletes = [c for c in transport.mutating_calls if c[1].endswith("/delete")]
        assert len(creates) == 1
        assert len(registers) == 6  # exactly once per selected image
        assert len(deletes) == 0    # success path → no delete
        # Every extra call caused by polling was a read (GET), never a mutation.
        assert transport.get_faces_count >= 4
        session.close()
