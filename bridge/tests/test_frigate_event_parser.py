"""T034-A parser tests (Feature 001) — cases A–J, plus the 2026-09-17 Shape-B correction.

Pure, offline, stdlib-only. Validates the CORRECTED Frigate 0.17.2 wire contract: both
sub_label shapes (Shape A: scalar string + separate sub_label_score; Shape B: legacy
[name, score] 2-element array, Frigate's ACTUAL shape for a genuine positive match) are
accepted; anything else is malformed. after.score/top_score (detection) are never
conflated with recognition confidence, for either shape. No HA, no Frigate, no
enrollment DB.
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
    # A valid 2-elem [name, score] array is Shape B (see test_ShapeB_* below) — NOT
    # malformed. These remaining shapes have no valid interpretation and stay malformed.
    for bad in [{"name": "Known_Person_A"}, 123, ""]:
        r = parse_event(_event({
            "id": "h", "camera": "front_door", "label": "person",
            "sub_label": bad, "score": 0.8,
        }))
        assert r.outcome is ParseOutcome.PERSON_EVENT
        assert r.has_recognized_identity is False, f"{bad!r} wrongly treated as identity"
        assert r.sub_label is None


# Shape B — the corrected 2026-09-17 [name, score] legacy array contract ----
def test_ShapeB_valid_array_extracts_identity_and_score():
    r = parse_event(_event({
        "id": "shapeb-1", "camera": "front_door", "label": "person",
        "sub_label": ["Known_Person_B", 0.93], "score": 0.84,
    }))
    assert r.outcome is ParseOutcome.PERSON_EVENT
    assert r.sub_label == "Known_Person_B"
    assert r.has_recognized_identity is True
    assert r.sub_label_score == 0.93            # from the array, not a separate field
    assert r.detection_score == 0.84            # detection stays separate
    assert r.error is None


def test_ShapeB_tuple_also_accepted():
    # JSON never produces a Python tuple, but the parser accepts either sequence type.
    r = parse_event(_event({
        "id": "shapeb-tuple", "camera": "front_door", "label": "person",
        "sub_label": ("Known_Person_B", 0.9), "score": 0.8,
    }))
    assert r.sub_label == "Known_Person_B"
    assert r.sub_label_score == 0.9


def test_ShapeB_fails_closed_on_malformed_variants():
    bad_arrays = [
        [],                                  # empty
        ["Known_Person_B"],                   # length 1
        ["Known_Person_B", 0.93, "extra"],    # length 3
        ["", 0.93],                          # empty identity
        ["   ", 0.93],                       # whitespace-only identity
        [None, 0.93],                        # null identity
        ["Known_Person_B", None],            # null score
        ["Known_Person_B", "0.93"],          # numeric STRING score — not permitted
        ["Known_Person_B", True],            # bool score must NOT count as numeric
        [{"n": "x"}, 0.93],                  # non-string identity element
    ]
    for bad in bad_arrays:
        r = parse_event(_event({
            "id": "shapeb-bad", "camera": "front_door", "label": "person",
            "sub_label": bad, "score": 0.8,
        }))
        assert r.has_recognized_identity is False, f"{bad!r} wrongly treated as identity"
        assert r.sub_label is None
        assert r.error is not None


def test_ShapeB_nan_and_inf_scores_pass_the_parser_but_fail_closed_downstream():
    # The parser only decides shape well-formedness; NaN/inf rejection happens in
    # identity_normalizer._valid_score (see test_identity_normalizer.py), uniformly for
    # both shapes. Document that behavior here so the split responsibility stays visible.
    import math
    for bad_score in (math.nan, math.inf, -math.inf):
        r = parse_event(_event({
            "id": "shapeb-nonfinite", "camera": "front_door", "label": "person",
            "sub_label": ["Known_Person_B", bad_score], "score": 0.8,
        }))
        assert r.has_recognized_identity is True   # shape is well-formed
        assert r.sub_label_score is not None        # raw float passed through, as-is
        assert not math.isfinite(r.sub_label_score)  # NaN/inf rejection is downstream


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


# Sanitized real-shape fixture (captured live positive match, 2026-09-17) ---
def test_fixture_known_person_real_shape():
    payload = json.loads((FIXTURES / "frigate_event_known.json").read_text())
    r = parse_event(payload)
    assert r.outcome is ParseOutcome.PERSON_EVENT
    assert r.camera == "front_door"
    assert r.has_recognized_identity is True
    assert r.sub_label == "Person_B"
    assert r.sub_label_score == 0.93
    assert r.detection_score == 0.84375
