"""AuditService — append-only records without biometric content (T005, FR-031)."""

from __future__ import annotations

from app.models.audit import AuditLogEntry
from app.models.enums import AuditAction
from app.services.audit_service import AuditService


def test_record_and_read_back(app):
    with app.state.session_factory() as session:
        service = AuditService(session)
        service.record(
            AuditAction.PERSON_CREATED,
            entity_type="person",
            entity_id="abc-123",
            details={"display_name_len": 5},
        )
        session.commit()

        entry = session.query(AuditLogEntry).one()
        assert entry.action == "PERSON_CREATED"
        assert entry.entity_type == "person"
        assert entry.entity_id == "abc-123"
        assert entry.details == {"display_name_len": 5}
        assert entry.timestamp is not None


def test_audit_is_append_only(app):
    with app.state.session_factory() as session:
        for i in range(3):
            AuditService(session).record(AuditAction.PERSON_UPDATED, entity_id=str(i))
        session.commit()
        entries = session.query(AuditLogEntry).all()
        assert len(entries) == 3
        # No column could hold image bytes: details is JSON, and nothing else is free-form.
        for e in entries:
            assert isinstance(e.details, (dict, type(None)))