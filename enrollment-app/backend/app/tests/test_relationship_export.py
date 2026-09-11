"""T034-B relationship-mapping export tests (Feature 001) — cases A–J.

Deterministic, offline. Builds synthetic Person rows (Known_Person_A/B — never the real
household name) in a temp SQLite DB and exercises the read-only export generator.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.config import Settings, FrigateConfig
from app.db import make_session_factory
from app.models.enums import EnrollmentStatus
from app.models.person import Person
from app.tools.relationship_export import (
    RelationshipExportError,
    build_document,
    build_entries,
    export_mapping,
)


def _session(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", frigate=FrigateConfig())
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    factory = make_session_factory(settings.db_path)
    return factory()


def _add(session, *, name="Known_Person_A", frigate_name="Known_Person_A",
         relationship="Family", enabled=True, status=EnrollmentStatus.ENROLLED.value,
         person_id=None, frigate_identity=...):
    p = Person(
        id=person_id or str(uuid.uuid4()),
        display_name=name,
        relationship=relationship,
        enabled=enabled,
        enrollment_status=status,
        frigate_identity_name=(frigate_name if frigate_identity is ... else frigate_identity),
    )
    session.add(p)
    session.flush()
    return p


# A. enrolled + enabled -----------------------------------------------------
def test_A_enrolled_enabled_exported(tmp_path):
    s = _session(tmp_path)
    _add(s, name="Known Person A", frigate_name="Known_Person_A", relationship="Family", enabled=True)
    s.commit()
    doc = build_document(build_entries(s))
    e = doc["identities"]["Known_Person_A"]
    assert e["relationship"] == "Family"
    assert e["enabled"] is True
    assert e["display_name"] == "Known Person A"
    assert e["person_uuid"]
    s.close()


# B. enrolled + disabled -> present with enabled=false ----------------------
def test_B_enrolled_disabled_present_false(tmp_path):
    s = _session(tmp_path)
    _add(s, frigate_name="Known_Person_A", enabled=False)
    s.commit()
    doc = build_document(build_entries(s))
    assert "Known_Person_A" in doc["identities"]           # NOT omitted
    assert doc["identities"]["Known_Person_A"]["enabled"] is False
    s.close()


# C. not enrolled -> not exported ------------------------------------------
def test_C_not_enrolled_excluded(tmp_path):
    s = _session(tmp_path)
    _add(s, frigate_name="Known_Person_A", status=EnrollmentStatus.READY.value)
    _add(s, name="B", frigate_name="Known_Person_B", status=EnrollmentStatus.NOT_READY.value)
    s.commit()
    doc = build_document(build_entries(s))
    assert doc["identities"] == {}
    s.close()


# D. missing frigate_identity_name -> not exportable ------------------------
def test_D_missing_frigate_identity_excluded(tmp_path):
    s = _session(tmp_path)
    # ENROLLED but frigate_identity_name is NULL → not a candidate at all
    _add(s, frigate_identity=None)
    s.commit()
    doc = build_document(build_entries(s))
    assert doc["identities"] == {}
    s.close()


# E. duplicate frigate_identity_name -> export FAILS safely -----------------
def test_E_duplicate_identity_fails(tmp_path):
    s = _session(tmp_path)
    # DB unique constraint would normally prevent this; simulate by bypassing via two rows
    # that both end up with the same frigate_identity_name is not allowed by UNIQUE.
    # Instead, force the in-memory validation path: monkeypatch candidates.
    from app.tools import relationship_export as re_mod
    p1 = _add(s, name="A", frigate_name="Dup_Name", person_id=str(uuid.uuid4()))
    p2 = Person(id=str(uuid.uuid4()), display_name="B", relationship="Friend",
                enabled=True, enrollment_status=EnrollmentStatus.ENROLLED.value,
                frigate_identity_name="Dup_Name_other")
    s.add(p2); s.flush()
    # Simulate the duplicate by patching the candidate query to return two same-name rows.
    p2.frigate_identity_name = "Dup_Name"  # in-memory only (not committed / not flushed to unique index)
    orig = re_mod._candidate_persons
    re_mod._candidate_persons = lambda session: [p1, p2]
    try:
        with pytest.raises(RelationshipExportError):
            build_entries(s)
    finally:
        re_mod._candidate_persons = orig
    s.close()


# F. missing relationship -> fail-closed ------------------------------------
def test_F_missing_relationship_fails(tmp_path):
    s = _session(tmp_path)
    _add(s, frigate_name="Known_Person_A", relationship="")
    s.commit()
    with pytest.raises(RelationshipExportError):
        build_entries(s)
    s.close()


# G. invalid relationship -> fail ------------------------------------------
def test_G_invalid_relationship_fails(tmp_path):
    s = _session(tmp_path)
    _add(s, frigate_name="Known_Person_A", relationship="BestFriendForever")
    s.commit()
    with pytest.raises(RelationshipExportError):
        build_entries(s)
    s.close()


# H. deterministic ordering -------------------------------------------------
def test_H_deterministic_ordering(tmp_path):
    s = _session(tmp_path)
    _add(s, name="Z", frigate_name="Zeta", relationship="Friend")
    _add(s, name="A", frigate_name="Alpha", relationship="Family")
    _add(s, name="M", frigate_name="Mike", relationship="Neighbor")
    s.commit()
    keys = list(build_document(build_entries(s))["identities"].keys())
    assert keys == sorted(keys) == ["Alpha", "Mike", "Zeta"]
    s.close()


# I. atomic write -> no partial target on failure ---------------------------
def test_I_atomic_write_no_partial(tmp_path, monkeypatch):
    s = _session(tmp_path)
    _add(s, frigate_name="Known_Person_A")
    s.commit()
    target = tmp_path / "out" / "relationship_mapping.generated.json"
    # First, a real successful write to establish a baseline file.
    export_mapping(s, target)
    baseline = target.read_text()
    # Now force JSON rendering to fail mid-write; target must remain the baseline.
    import app.tools.relationship_export as re_mod

    def boom(*a, **k):
        raise RuntimeError("simulated serialization failure")

    monkeypatch.setattr(re_mod, "render_json", boom)
    with pytest.raises(RuntimeError):
        export_mapping(s, target)
    assert target.read_text() == baseline              # unchanged, not partial
    # no leftover temp files
    assert not list(target.parent.glob(".relmap.*.tmp"))
    s.close()


# J. privacy: tracked fixtures/tests contain synthetic names only -----------
def test_J_no_real_identity_in_tracked_sources():
    repo = Path(__file__).resolve().parents[4]  # repo root
    # Build the forbidden household token from fragments so this test file itself never
    # contains the literal (avoids a self-referential false positive).
    forbidden = "Prav" + "een"
    tracked = [
        repo / "enrollment-app/backend/app/tools/relationship_export.py",
        repo / "enrollment-app/backend/app/tests/test_relationship_export.py",
        repo / "specs/001-front-door-person-identification/contracts/relationship-mapping.generated.sample.json",
    ]
    for f in tracked:
        text = f.read_text()
        assert forbidden not in text, f"real household name leaked into {f}"


# Round-trip: written JSON is valid + matches build_document ----------------
def test_written_json_matches_document(tmp_path):
    s = _session(tmp_path)
    _add(s, name="Known Person A", frigate_name="Known_Person_A", relationship="Family")
    _add(s, name="Known Person B", frigate_name="Known_Person_B", relationship="Neighbor", enabled=False)
    s.commit()
    target = tmp_path / "relationship_mapping.generated.json"
    written = export_mapping(s, target, generated_at=None)
    on_disk = json.loads(target.read_text())
    assert on_disk == written
    assert on_disk["schema_version"] == 1
    assert "generated_at" not in on_disk                # omitted when None (deterministic)
    assert set(on_disk["identities"]) == {"Known_Person_A", "Known_Person_B"}
    s.close()
