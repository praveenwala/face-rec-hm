"""T034-A parser tests (Feature 001) — cases A–J.

Pure, offline, stdlib-only. Validates the verified Frigate 0.17.2 wire contract:
scalar sub_label (string|null), separate sub_label_score (recognition), after.score
(detection) — never conflated. No HA, no Frigate, no enrollment DB.
"""

from __future__ import annotations

import json
from pathlib import Path

from bridge.frigate_event_parser import (
    Availability,
    ParseOutcome,
    parse_availability,
    parse_event,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _event(after: dict, type_="update") -> dict:
    return {"type": type_, "before": {}, "after": after}


# A. Known person -----------------------------------------------------------
def test_A_known_person_identity_and_recognition_score():
    r = parse_event(_event({
        "id": "evt-1", "camera": "front_door", "label": "person",
        "sub_label": "Known_Person_A", "sub_label_score": 0.93,
        "score": 0.84, "top_score": 0.86, "start_time": 1.0, "end_time": None,
        "false_positive": False,
    }))
    assert r.outcome is ParseOutcome.PERSON_EVENT
    assert r.sub_label == "Known_Person_A"
    assert r.has_recognized_identity is True
    assert r.sub_label_score == 0.93           # recognition confidence from sub_label_score
    assert r.detection_score == 0.84           # detection kept separate


# B. Unknown person ---------------------------------------------------------
def test_B_unknown_person_no_identity():
    r = parse_event(_event({
        "id": "evt-2", "camera": "front_door", "label": "person",
        "sub_label": None, "score": 0.80,
    }))
    assert r.outcome is ParseOutcome.PERSON_EVENT
    assert r.sub_label is None
    assert r.has_recognized_identity is False
    assert r.sub_label_score is None


# C. CRITICAL score separation ---------------------------------------------
def test_C_score_separation_detection_vs_recognition():
    r = parse_event(_event({
        "id": "evt-3", "camera": "front_door", "label": "person",
        "sub_label": "Known_Person_A", "sub_label_score": 0.93, "score": 0.84,
    }))
    assert r.detection_score == 0.84
    assert r.sub_label_score == 0.93
    assert r.detection_score != r.sub_label_score


# D. No recognition score — never substitute detection score ----------------
def test_D_missing_recognition_score_never_uses_detection():
    r = parse_event(_event({
        "id": "evt-4", "camera": "front_door", "label": "person",
        "sub_label": "Known_Person_A", "score": 0.84,  # no sub_label_score
    }))
    assert r.sub_label == "Known_Person_A"
    assert r.sub_label_score is None           # explicit null, NOT 0.84
    assert r.detection_score == 0.84

def test_D2_unknown_without_recognition_score():
    r = parse_event(_event({
        "id": "evt-4b", "camera": "front_door", "label": "person",
        "sub_label": None, "score": 0.80,
    }))
    assert r.sub_label_score is None


# E. Non-person event -> ignored safely -------------------------------------
def test_E_non_person_ignored():
    for lbl in ("car", "dog", "cat"):
        r = parse_event(_event({"id": "e", "camera": "front_door", "label": lbl, "sub_label": "whatever"}))
        assert r.outcome is ParseOutcome.IGNORED_NON_PERSON
        assert r.has_recognized_identity is False
        assert r.sub_label is None


# F. Invalid JSON -----------------------------------------------------------
def test_F_invalid_json_safe_failure():
    r = parse_event("{not valid json")
    assert r.outcome is ParseOutcome.PARSE_ERROR
    assert r.sub_label is None
    assert r.has_recognized_identity is False


# G. Missing after ----------------------------------------------------------
def test_G_missing_after_safe_failure():
    r = parse_event({"type": "update", "before": {}})
    assert r.outcome is ParseOutcome.PARSE_ERROR
    assert r.has_recognized_identity is False


# H. Malformed sub_label -> never treated as known --------------------------
def test_H_malformed_sub_label_never_known():
    # legacy [name, score] array must NOT be interpreted as an identity
    for bad in [["Known_Person_A", 0.93], {"name": "Known_Person_A"}, 123, ""]:
        r = parse_event(_event({
            "id": "h", "camera": "front_door", "label": "person",
            "sub_label": bad, "score": 0.8,
        }))
        assert r.outcome is ParseOutcome.PERSON_EVENT
        assert r.has_recognized_identity is False, f"{bad!r} wrongly treated as identity"
        assert r.sub_label is None


# I. Event lifecycle correlation -------------------------------------------
def test_I_lifecycle_same_event_id_correlation():
    eid = "1700000000.111111-abcxyz"
    parses = [
        parse_event(_event({"id": eid, "camera": "front_door", "label": "person", "sub_label": None}, type_=t))
        for t in ("new", "update", "end")
    ]
    assert [p.lifecycle for p in parses] == ["new", "update", "end"]
    assert {p.event_id for p in parses} == {eid}  # same correlation id across lifecycle


# J. Availability online/offline -------------------------------------------
def test_J_availability_parsing():
    assert parse_availability("online") is Availability.ONLINE
    assert parse_availability("offline") is Availability.OFFLINE
    assert parse_availability(b"online") is Availability.ONLINE
    assert parse_availability('"online"') is Availability.ONLINE
    assert parse_availability("garbage") is Availability.UNKNOWN
    assert parse_availability("") is Availability.UNKNOWN


# Sanitized real-shape fixture parses as an unknown person event ------------
def test_fixture_unknown_person_real_shape():
    payload = json.loads((FIXTURES / "frigate_event_unknown.json").read_text())
    r = parse_event(payload)
    assert r.outcome is ParseOutcome.PERSON_EVENT
    assert r.camera == "front_door"
    assert r.has_recognized_identity is False
    assert r.detection_score == 0.8046875
    assert r.top_score == 0.84375
    assert r.sub_label_score is None
