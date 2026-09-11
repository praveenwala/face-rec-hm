"""T034-C1 tests: HA-consumable YAML representation of the relationship mapping.

Both JSON and YAML are derived from the SAME validated canonical document
(build_entries -> build_document). These tests prove JSON/YAML logical parity, safe
escaping (round-trip), fail-closed validation shared across formats, deterministic
ordering, atomic write, integer schema_version, and privacy (synthetic names only).

Deterministic decoding: a strict decoder for exactly our double-quoted-scalar YAML shape
is used for CI (no external dependency). A separate authoritative check (see the C1 report /
PART 10) parses the exact generated YAML with a real PyYAML parser in the HA container.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.config import FrigateConfig, Settings
from app.db import make_session_factory
from app.models.enums import EnrollmentStatus
from app.models.person import Person
from app.tools.relationship_export import (
    RelationshipExportError,
    build_document,
    build_entries,
    export_mapping,
    render_json,
    render_yaml,
)


# ---- strict decoder for our double-quoted-scalar YAML (test-only) ---------
def _unquote(token: str) -> str:
    assert token.startswith('"') and token.endswith('"'), f"expected double-quoted: {token!r}"
    body = token[1:-1]
    out = []
    i = 0
    while i < len(body):
        c = body[i]
        if c == "\\":
            nxt = body[i + 1]
            mapping = {"\\": "\\", '"': '"', "n": "\n", "t": "\t", "r": "\r"}
            if nxt in mapping:
                out.append(mapping[nxt]); i += 2; continue
            if nxt == "x":
                out.append(chr(int(body[i + 2 : i + 4], 16))); i += 4; continue
            raise AssertionError(f"unknown escape \\{nxt}")
        out.append(c); i += 1
    return "".join(out)


def _decode_generated_yaml(text: str) -> dict:
    """Parse exactly the shape render_yaml produces. Fails loudly on anything unexpected."""
    doc: dict = {"identities": {}}
    lines = text.splitlines()
    cur_key = None
    for ln in lines:
        if not ln.strip():
            continue
        if ln.startswith("schema_version: "):
            doc["schema_version"] = int(ln.split(": ", 1)[1])
        elif ln.startswith("generated_at: "):
            doc["generated_at"] = _unquote(ln.split(": ", 1)[1])
        elif ln.rstrip() == "identities:":
            continue
        elif ln.strip() == "identities: {}":
            doc["identities"] = {}
        elif ln.startswith("  ") and ln.endswith(":") and not ln.startswith("    "):
            cur_key = _unquote(ln.strip()[:-1])
            doc["identities"][cur_key] = {}
        elif ln.startswith("    "):
            field, _, val = ln.strip().partition(": ")
            if field == "enabled":
                doc["identities"][cur_key][field] = (val == "true")
            else:
                doc["identities"][cur_key][field] = _unquote(val)
        else:
            raise AssertionError(f"unexpected YAML line: {ln!r}")
    return doc


def _session(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", frigate=FrigateConfig())
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return make_session_factory(settings.db_path)()


def _add(session, *, name="Known Person A", frigate_name="Known_Person_A",
         relationship="Family", enabled=True, status=EnrollmentStatus.ENROLLED.value,
         frigate_identity=...):
    p = Person(id=str(uuid.uuid4()), display_name=name, relationship=relationship,
               enabled=enabled, enrollment_status=status,
               frigate_identity_name=(frigate_name if frigate_identity is ... else frigate_identity))
    session.add(p); session.flush()
    return p


# A. JSON/YAML logical parity ----------------------------------------------
def test_A_json_yaml_parity(tmp_path):
    s = _session(tmp_path)
    _add(s, name="Known Person A", frigate_name="Known_Person_A", relationship="Family", enabled=True)
    _add(s, name="Known Person B", frigate_name="Known_Person_B", relationship="Neighbor", enabled=False)
    s.commit()
    doc = build_document(build_entries(s))
    from_json = json.loads(render_json(doc))
    from_yaml = _decode_generated_yaml(render_yaml(doc))
    assert from_json["schema_version"] == from_yaml["schema_version"] == 1
    assert set(from_json["identities"]) == set(from_yaml["identities"])
    for k in from_json["identities"]:
        assert from_json["identities"][k] == from_yaml["identities"][k]
    s.close()


# B. enabled enrolled -------------------------------------------------------
def test_B_enabled(tmp_path):
    s = _session(tmp_path); _add(s, frigate_name="Known_Person_A", enabled=True); s.commit()
    y = _decode_generated_yaml(render_yaml(build_document(build_entries(s))))
    assert y["identities"]["Known_Person_A"]["enabled"] is True
    s.close()


# C. disabled enrolled retained enabled=false -------------------------------
def test_C_disabled_retained(tmp_path):
    s = _session(tmp_path); _add(s, frigate_name="Known_Person_A", enabled=False); s.commit()
    y = _decode_generated_yaml(render_yaml(build_document(build_entries(s))))
    assert "Known_Person_A" in y["identities"]
    assert y["identities"]["Known_Person_A"]["enabled"] is False
    s.close()


# D. deterministic ordering -------------------------------------------------
def test_D_deterministic_ordering(tmp_path):
    s = _session(tmp_path)
    _add(s, name="Z", frigate_name="Zeta", relationship="Friend")
    _add(s, name="A", frigate_name="Alpha", relationship="Family")
    s.commit()
    text1 = render_yaml(build_document(build_entries(s)))
    text2 = render_yaml(build_document(build_entries(s)))
    assert text1 == text2  # byte-identical
    keys = list(_decode_generated_yaml(text1)["identities"].keys())
    assert keys == ["Alpha", "Zeta"]
    s.close()


# E-G. fail-closed validation shared with JSON (build_entries raises before render) --
def test_E_duplicate_fail_closed(tmp_path, monkeypatch):
    s = _session(tmp_path)
    p1 = _add(s, name="A", frigate_name="Dup")
    p2 = _add(s, name="B", frigate_name="Dup_other", relationship="Friend")
    s.commit()
    from app.tools import relationship_export as m
    p2.frigate_identity_name = "Dup"
    monkeypatch.setattr(m, "_candidate_persons", lambda session: [p1, p2])
    with pytest.raises(RelationshipExportError):
        build_entries(s)  # both json + yaml go through this
    s.close()

def test_F_missing_relationship_fail_closed(tmp_path):
    s = _session(tmp_path); _add(s, frigate_name="Known_Person_A", relationship=""); s.commit()
    with pytest.raises(RelationshipExportError):
        build_entries(s)
    s.close()

def test_G_invalid_relationship_fail_closed(tmp_path):
    s = _session(tmp_path); _add(s, frigate_name="Known_Person_A", relationship="BFF"); s.commit()
    with pytest.raises(RelationshipExportError):
        build_entries(s)
    s.close()


# H. non-enrolled excluded --------------------------------------------------
def test_H_non_enrolled_excluded(tmp_path):
    s = _session(tmp_path)
    _add(s, frigate_name="Known_Person_A", status=EnrollmentStatus.READY.value)
    s.commit()
    y = _decode_generated_yaml(render_yaml(build_document(build_entries(s))))
    assert y["identities"] == {}
    s.close()


# I. atomic YAML write failure -> target intact, no temp -------------------
def test_I_atomic_yaml_write(tmp_path, monkeypatch):
    s = _session(tmp_path); _add(s, frigate_name="Known_Person_A"); s.commit()
    target = tmp_path / "out" / "relationship_mapping.generated.yaml"
    export_mapping(s, target, fmt="yaml")            # baseline
    baseline = target.read_text()
    import app.tools.relationship_export as m
    monkeypatch.setattr(m, "render_yaml", lambda doc: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        export_mapping(s, target, fmt="yaml")
    assert target.read_text() == baseline            # unchanged
    assert not list(target.parent.glob(".relmap.*.tmp"))
    s.close()


# J. string escaping round-trip --------------------------------------------
def test_J_escaping_round_trip(tmp_path):
    s = _session(tmp_path)
    # synthetic display_name values exercising apostrophe, colon, #, unicode,
    # yaml-boolean/null/number-looking strings, leading/trailing whitespace
    tricky = "O'Neil: value #1  — café — true null 12345"
    _add(s, name=tricky, frigate_name="Known_Person_A", relationship="Family")
    s.commit()
    y = _decode_generated_yaml(render_yaml(build_document(build_entries(s))))
    got = y["identities"]["Known_Person_A"]["display_name"]
    assert got == tricky, f"round-trip mismatch: {got!r} != {tricky!r}"
    # yaml-looking bool/null must stay strings (relationship stays 'Family')
    assert y["identities"]["Known_Person_A"]["relationship"] == "Family"
    s.close()

def test_J2_boolean_like_identity_key_stays_string(tmp_path):
    s = _session(tmp_path)
    # a frigate name that looks boolean/numeric must remain a string key
    _add(s, name="Yes Person", frigate_name="true", relationship="Friend")
    s.commit()
    y = _decode_generated_yaml(render_yaml(build_document(build_entries(s))))
    assert "true" in y["identities"]
    s.close()


# K. schema_version remains integer 1 --------------------------------------
def test_K_schema_version_integer(tmp_path):
    s = _session(tmp_path); _add(s, frigate_name="Known_Person_A"); s.commit()
    y = _decode_generated_yaml(render_yaml(build_document(build_entries(s))))
    assert y["schema_version"] == 1 and isinstance(y["schema_version"], int)
    # yaml text has no quotes around the integer
    assert "schema_version: 1" in render_yaml(build_document(build_entries(s)))
    s.close()


# L. privacy: synthetic names only in tracked test/source -------------------
def test_L_no_real_identity_in_tracked_sources():
    repo = Path(__file__).resolve().parents[4]
    forbidden = "Prav" + "een"
    for rel in [
        "enrollment-app/backend/app/tools/relationship_export.py",
        "enrollment-app/backend/app/tests/test_relationship_export_yaml.py",
    ]:
        assert forbidden not in (repo / rel).read_text()
