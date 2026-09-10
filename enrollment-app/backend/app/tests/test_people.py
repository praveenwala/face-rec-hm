"""Phase 2 tests — people CRUD, relationship enum, enable/disable, safe delete,
enrolled-delete protection, and audit events (T009–T015, G2).

Synthetic names only — never real household identities (spec privacy rules).
"""

from __future__ import annotations

import uuid

import pytest

from app.models.enums import AuditAction

VALID_UUID = "00000000-0000-4000-8000-000000000001"


def _create(client, name="Praveen Tester", relationship="Family"):
    return client.post(
        "/api/people",
        json={"display_name": name, "relationship": relationship},
    )


# ---- create ---------------------------------------------------------------


def test_create_person_valid(client):
    resp = _create(client, name="Test Person", relationship="Neighbor")
    assert resp.status_code == 201
    body = resp.json()
    assert body["display_name"] == "Test Person"
    assert body["relationship"] == "Neighbor"
    assert body["enabled"] is True
    assert body["enrollment_status"] == "DRAFT"
    # Never an identifier: UUID is server-generated, frigate name stays NULL pre-Phase-6.
    uuid.UUID(body["id"])
    assert body["frigate_identity_name"] is None
    assert body["photo_count"] == 0
    assert body["suitable_count"] == 0
    assert body["representative_photo_url"] is None


def test_create_person_trims_whitespace(client):
    body = _create(client, name="  Spaces Around  ", relationship="Friend").json()
    assert body["display_name"] == "Spaces Around"


def test_create_person_missing_display_name(client):
    resp = client.post("/api/people", json={"relationship": "Family"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_person_whitespace_only_name(client):
    resp = _create(client, name="   ")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_person_invalid_relationship(client):
    resp = client.post(
        "/api/people", json={"display_name": "X", "relationship": "Coworker"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_person_rejects_extra_fields(client):
    resp = client.post(
        "/api/people",
        json={
            "display_name": "X",
            "relationship": "Family",
            "frigate_identity_name": "sneaky",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# ---- list -----------------------------------------------------------------


def test_list_people_empty(client):
    resp = client.get("/api/people")
    assert resp.status_code == 200
    assert resp.json() == {"people": []}


def test_list_people_multiple_preserves_relationships(client):
    _create(client, name="Alpha", relationship="Family")
    _create(client, name="Beta", relationship="Friend")
    _create(client, name="Gamma", relationship="Other Known")
    people = client.get("/api/people").json()["people"]
    assert len(people) == 3
    by_name = {p["display_name"]: p for p in people}
    assert by_name["Alpha"]["relationship"] == "Family"
    assert by_name["Beta"]["relationship"] == "Friend"
    assert by_name["Gamma"]["relationship"] == "Other Known"
    # Flat collection — grouping is a frontend concern (contracts/rest-api.md).
    assert all(p["enabled"] for p in people)


# ---- get ------------------------------------------------------------------


def test_get_person_valid(client):
    created = _create(client).json()
    resp = client.get(f"/api/people/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_person_unknown(client):
    resp = client.get(f"/api/people/{VALID_UUID}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PERSON_NOT_FOUND"


def test_get_person_malformed_uuid(client):
    resp = client.get("/api/people/not-a-uuid")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# ---- patch -----------------------------------------------------------------


def test_patch_rename_keeps_uuid_and_frigate_name(client):
    created = _create(client).json()
    resp = client.patch(
        f"/api/people/{created['id']}", json={"display_name": "Renamed Person"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["display_name"] == "Renamed Person"
    assert body["id"] == created["id"]  # UUID immutable
    assert body["frigate_identity_name"] is None  # rename never fabricates identity


def test_patch_relationship_change(client):
    created = _create(client, relationship="Family").json()
    resp = client.patch(
        f"/api/people/{created['id']}", json={"relationship": "Friend"}
    )
    assert resp.json()["relationship"] == "Friend"


def test_patch_disable_and_enable(client):
    created = _create(client).json()
    assert created["enabled"] is True

    resp = client.patch(f"/api/people/{created['id']}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    # Disabling preserves the record — distinct from delete.
    assert client.get(f"/api/people/{created['id']}").json()["enabled"] is False

    resp = client.patch(f"/api/people/{created['id']}", json={"enabled": True})
    assert resp.json()["enabled"] is True


def test_patch_invalid_relationship(client):
    created = _create(client).json()
    resp = client.patch(
        f"/api/people/{created['id']}", json={"relationship": "Coworker"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_immutable_field_rejected(client):
    created = _create(client).json()
    resp = client.patch(
        f"/api/people/{created['id']}",
        json={"frigate_identity_name": "should-not-stick"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    # And it did not stick.
    assert client.get(f"/api/people/{created['id']}").json()["frigate_identity_name"] is None


def test_patch_unknown_person(client):
    resp = client.patch(f"/api/people/{VALID_UUID}", json={"enabled": False})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PERSON_NOT_FOUND"


def test_patch_noop_does_not_emit_audit(client):
    created = _create(client).json()
    before = client.get("/api/audit").json()["entries"]
    resp = client.patch(
        f"/api/people/{created['id']}",
        json={"display_name": created["display_name"], "enabled": True},
    )
    assert resp.status_code == 200
    after = client.get("/api/audit").json()["entries"]
    assert len(after) == len(before)  # no-op patch: no audit noise


# ---- delete ----------------------------------------------------------------


def test_delete_non_enrolled_person(client):
    created = _create(client).json()
    resp = client.delete(f"/api/people/{created['id']}")
    assert resp.status_code == 204
    assert (
        client.get(f"/api/people/{created['id']}").status_code == 404
    )


def test_delete_unknown_person(client):
    resp = client.delete(f"/api/people/{VALID_UUID}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PERSON_NOT_FOUND"


def test_delete_enrolled_person_refused(client, app):
    """Enrolled-state delete must be refused — no orphaned biometric enrollment
    (FR-026). Phase 2 simulates ENROLLED by setting the field directly; Phase 6
    is what would legitimately set it."""
    created = _create(client).json()
    with app.state.session_factory() as session:
        from app.models.person import Person

        person = session.get(Person, created["id"])
        person.enrollment_status = "ENROLLED"
        session.commit()

    resp = client.delete(f"/api/people/{created['id']}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ENROLLED_PERSON_DELETE_REFUSED"
    # Record still exists — nothing was silently deleted.
    assert client.get(f"/api/people/{created['id']}").status_code == 200


def test_delete_whitespace_only_after_trim(client):
    created = _create(client, name="  Trim Me  ").json()
    assert created["display_name"] == "Trim Me"
    assert client.delete(f"/api/people/{created['id']}").status_code == 204


# ---- audit events -----------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "steps"),
    [
        ("PERSON_CREATED", lambda c, pid: None),
        ("PERSON_UPDATED", lambda c, pid: c.patch(f"/api/people/{pid}", json={"display_name": "New Name"})),
        ("RELATIONSHIP_CHANGED", lambda c, pid: c.patch(f"/api/people/{pid}", json={"relationship": "Neighbor"})),
        ("PERSON_DISABLED", lambda c, pid: c.patch(f"/api/people/{pid}", json={"enabled": False})),
        ("PERSON_ENABLED", lambda c, pid: (c.patch(f"/api/people/{pid}", json={"enabled": False}), c.patch(f"/api/people/{pid}", json={"enabled": True}))),
        ("PERSON_DELETED", lambda c, pid: c.delete(f"/api/people/{pid}")),
    ],
)
def test_audit_events_emitted(client, action, steps):
    created = _create(client).json()
    steps(client, created["id"])

    entries = client.get(f"/api/audit?person_id={created['id']}").json()["entries"]
    actions = [e["action"] for e in entries]
    assert action in actions
    # Audit entries never carry biometric content — only structured metadata.
    for e in entries:
        assert e["details"] is None or isinstance(e["details"], dict)
        assert e["entity_type"] == "person"
        assert e["entity_id"] == created["id"]


def test_audit_entries_newest_first(client):
    created = _create(client).json()
    client.patch(f"/api/people/{created['id']}", json={"relationship": "Friend"})
    entries = client.get(f"/api/audit").json()["entries"]
    ids = [e["id"] for e in entries]
    assert ids == sorted(ids, reverse=True)


def test_audit_relationship_change_records_before_after(client):
    created = _create(client, relationship="Family").json()
    client.patch(f"/api/people/{created['id']}", json={"relationship": "Other Known"})
    entries = client.get(f"/api/audit?person_id={created['id']}").json()["entries"]
    rel_events = [e for e in entries if e["action"] == "RELATIONSHIP_CHANGED"]
    assert len(rel_events) == 1
    assert rel_events[0]["details"] == {"from": "Family", "to": "Other Known"}


def test_audit_malformed_person_filter(client):
    resp = client.get("/api/audit?person_id=not-a-uuid")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# ---- relationships endpoint --------------------------------------------------


def test_relationships_endpoint(client):
    resp = client.get("/api/relationships")
    assert resp.status_code == 200
    assert resp.json() == {
        "relationships": ["Family", "Friend", "Neighbor", "Other Known"]
    }