"""T034-C2.1 reference normalizer tests (Feature 001) — cases A–V.

Pure, offline, stdlib-only. Uses the real T034-A parser to produce FrigateEventParse
inputs where useful (ensuring C2.1 semantics stay consistent with T034-A). Synthetic
identities only.
"""

from __future__ import annotations

import math

from bridge.frigate_event_parser import parse_event, ParseOutcome
from bridge.identity_normalizer import (
    ALLOWED_RELATIONSHIPS,
    IdentityNormalizationResult,
    MappingStatus,
    Outcome,
    normalize_identity,
)


def _parse(after: dict, type_="update"):
    return parse_event({"type": type_, "before": {}, "after": after})


def _mapping(entries: dict, schema=1) -> dict:
    return {"schema_version": schema, "identities": entries}


_KNOWN_ENTRY = {
    "Known_Person_A": {
        "person_uuid": "00000000-0000-0000-0000-00000000000a",
        "display_name": "Known Person A",
        "relationship": "Family",
        "enabled": True,
    }
}


# A. known enabled ----------------------------------------------------------
def test_A_known_enabled():
    pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                 "sub_label": "Known_Person_A", "sub_label_score": 0.93, "score": 0.84})
    r = normalize_identity(pe, _mapping(_KNOWN_ENTRY), MappingStatus.LOADED)
    assert r.outcome == Outcome.IDENTITY_KNOWN and r.known is True
    assert r.raw_identity == "Known_Person_A"
    assert r.identity == "Known Person A"
    assert r.person_uuid == "00000000-0000-0000-0000-00000000000a"
    assert r.relationship == "Family" and r.enabled is True
    assert r.recognition_confidence == 0.93 and r.detection_confidence == 0.84


# B. unknown (null sub_label) ----------------------------------------------
def test_B_unknown():
    pe = _parse({"id": "e", "camera": "front_door", "label": "person", "sub_label": None, "score": 0.80})
    r = normalize_identity(pe, _mapping(_KNOWN_ENTRY))
    assert r.outcome == Outcome.IDENTITY_UNKNOWN and r.known is False
    assert r.raw_identity is None and r.identity is None and r.relationship is None
    assert r.enabled is None and r.recognition_confidence is None
    assert r.detection_confidence == 0.80


# C. disabled ---------------------------------------------------------------
def test_C_disabled():
    m = _mapping({"Known_Person_B": {"person_uuid": "u", "display_name": "B",
                                      "relationship": "Neighbor", "enabled": False}})
    pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                 "sub_label": "Known_Person_B", "sub_label_score": 0.95, "score": 0.82})
    r = normalize_identity(pe, m)
    assert r.outcome == Outcome.IDENTITY_DISABLED and r.known is False
    assert r.raw_identity == "Known_Person_B"
    assert r.identity is None and r.person_uuid is None and r.relationship is None
    assert r.enabled is False
    assert r.recognition_confidence == 0.95 and r.detection_confidence == 0.82


# D. unmapped ---------------------------------------------------------------
def test_D_unmapped():
    pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                 "sub_label": "Nobody", "sub_label_score": 0.9, "score": 0.8})
    r = normalize_identity(pe, _mapping(_KNOWN_ENTRY))
    assert r.outcome == Outcome.IDENTITY_UNMAPPED and r.known is False
    assert r.raw_identity == "Nobody" and r.identity is None and r.enabled is None


# E. invalid relationship on enabled entry -> MAPPING_UNAVAILABLE ----------
def test_E_invalid_relationship():
    m = _mapping({"X": {"person_uuid": "u", "display_name": "X", "relationship": "BFF", "enabled": True}})
    pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                 "sub_label": "X", "sub_label_score": 0.9})
    r = normalize_identity(pe, m)
    assert r.outcome == Outcome.MAPPING_UNAVAILABLE and r.known is False


# F. mapping missing/unavailable -------------------------------------------
def test_F_mapping_missing():
    pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                 "sub_label": "Known_Person_A", "sub_label_score": 0.9})
    r = normalize_identity(pe, None, MappingStatus.MISSING)
    assert r.outcome == Outcome.MAPPING_UNAVAILABLE and r.known is False
    # mapping-not-a-dict even if status says loaded
    r2 = normalize_identity(pe, ["not a dict"], MappingStatus.LOADED)
    assert r2.outcome == Outcome.MAPPING_UNAVAILABLE


# G. unsupported schema -----------------------------------------------------
def test_G_unsupported_schema():
    pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                 "sub_label": "Known_Person_A", "sub_label_score": 0.9})
    r = normalize_identity(pe, _mapping(_KNOWN_ENTRY, schema=2))
    assert r.outcome == Outcome.MAPPING_UNAVAILABLE
    r2 = normalize_identity(pe, {"identities": _KNOWN_ENTRY})  # missing schema_version
    assert r2.outcome == Outcome.MAPPING_UNAVAILABLE


# H. malformed sub_label (from T034-A) -> RECOGNITION_FAILURE ---------------
def test_H_malformed_sub_label():
    # A valid 2-elem [name, score] array is Shape B (see test_ShapeB_* below) — NOT
    # malformed; these remaining shapes have no valid interpretation.
    for bad in [{"n": "x"}, 123]:
        pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                     "sub_label": bad, "sub_label_score": 0.9, "score": 0.8})
        assert pe.outcome is ParseOutcome.PERSON_EVENT and pe.has_recognized_identity is False
        r = normalize_identity(pe, _mapping(_KNOWN_ENTRY))
        assert r.outcome == Outcome.RECOGNITION_FAILURE and r.known is False
        assert r.identity is None


# Shape B — corrected 2026-09-17 [name, score] array reaches IDENTITY_KNOWN -
def test_ShapeB_array_sub_label_reaches_known():
    pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                 "sub_label": ["Known_Person_A", 0.93], "score": 0.84})
    assert pe.has_recognized_identity is True
    assert pe.sub_label == "Known_Person_A"
    assert pe.sub_label_score == 0.93
    r = normalize_identity(pe, _mapping(_KNOWN_ENTRY))
    assert r.outcome == Outcome.IDENTITY_KNOWN and r.known is True
    assert r.raw_identity == "Known_Person_A"
    assert r.identity == "Known Person A"
    assert r.recognition_confidence == 0.93 and r.detection_confidence == 0.84


def test_ShapeB_malformed_array_still_fails_closed():
    for bad in [[], ["Known_Person_A"], ["Known_Person_A", 0.9, "extra"],
                ["", 0.9], [None, 0.9], ["Known_Person_A", None],
                ["Known_Person_A", "0.9"], ["Known_Person_A", True]]:
        pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                     "sub_label": bad, "score": 0.8})
        r = normalize_identity(pe, _mapping(_KNOWN_ENTRY))
        assert r.outcome == Outcome.RECOGNITION_FAILURE and r.known is False
        assert r.identity is None


# I. empty/whitespace identity -> UNKNOWN ----------------------------------
def test_I_empty_identity():
    for empty in ["", "   "]:
        pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                     "sub_label": empty, "score": 0.8})
        r = normalize_identity(pe, _mapping(_KNOWN_ENTRY))
        assert r.outcome == Outcome.IDENTITY_UNKNOWN


# J. score separation -------------------------------------------------------
def test_J_score_separation():
    pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                 "sub_label": "Known_Person_A", "sub_label_score": 0.93, "score": 0.84})
    r = normalize_identity(pe, _mapping(_KNOWN_ENTRY))
    assert r.recognition_confidence == 0.93 and r.detection_confidence == 0.84
    assert r.recognition_confidence != r.detection_confidence


# K. missing recognition score -> RECOGNITION_FAILURE ----------------------
def test_K_missing_recognition_score():
    pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                 "sub_label": "Known_Person_A", "score": 0.84})  # no sub_label_score
    r = normalize_identity(pe, _mapping(_KNOWN_ENTRY))
    assert r.outcome == Outcome.RECOGNITION_FAILURE and r.known is False
    assert r.recognition_confidence is None
    assert r.detection_confidence == 0.84  # detection preserved, never substituted


# L. invalid recognition score (bool / NaN / inf) -> RECOGNITION_FAILURE ---
def test_L_invalid_recognition_score():
    # bool: parser coerces bool sub_label_score to None (rejected) -> missing => failure
    pe_bool = _parse({"id": "e", "camera": "front_door", "label": "person",
                      "sub_label": "Known_Person_A", "sub_label_score": True, "score": 0.8})
    assert normalize_identity(pe_bool, _mapping(_KNOWN_ENTRY)).outcome == Outcome.RECOGNITION_FAILURE
    # NaN / inf: construct a FrigateEventParse directly with those scores
    from bridge.frigate_event_parser import FrigateEventParse
    for bad in (math.nan, math.inf, -math.inf):
        pe = FrigateEventParse(outcome=ParseOutcome.PERSON_EVENT, label="person",
                               sub_label="Known_Person_A", has_recognized_identity=True,
                               sub_label_score=bad, detection_score=0.8)
        assert normalize_identity(pe, _mapping(_KNOWN_ENTRY)).outcome == Outcome.RECOGNITION_FAILURE


# M. non-person -> IGNORED_NON_PERSON --------------------------------------
def test_M_non_person():
    pe = _parse({"id": "e", "camera": "front_door", "label": "car", "sub_label": "whatever"})
    r = normalize_identity(pe, _mapping(_KNOWN_ENTRY))
    assert r.outcome == Outcome.IGNORED_NON_PERSON and r.known is False and r.identity is None


# N. wrong enabled type -> MAPPING_UNAVAILABLE -----------------------------
def test_N_wrong_enabled_type():
    for bad_enabled in ["true", 1, None]:
        m = _mapping({"X": {"person_uuid": "u", "display_name": "X",
                            "relationship": "Family", "enabled": bad_enabled}})
        pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                     "sub_label": "X", "sub_label_score": 0.9})
        assert normalize_identity(pe, m).outcome == Outcome.MAPPING_UNAVAILABLE


# O. missing UUID on enabled entry -> MAPPING_UNAVAILABLE -------------------
def test_O_missing_uuid():
    m = _mapping({"X": {"display_name": "X", "relationship": "Family", "enabled": True}})
    pe = _parse({"id": "e", "camera": "front_door", "label": "person", "sub_label": "X", "sub_label_score": 0.9})
    assert normalize_identity(pe, m).outcome == Outcome.MAPPING_UNAVAILABLE


# P. missing display_name on enabled entry -> MAPPING_UNAVAILABLE -----------
def test_P_missing_display_name():
    m = _mapping({"X": {"person_uuid": "u", "relationship": "Family", "enabled": True}})
    pe = _parse({"id": "e", "camera": "front_door", "label": "person", "sub_label": "X", "sub_label_score": 0.9})
    assert normalize_identity(pe, m).outcome == Outcome.MAPPING_UNAVAILABLE


# Q. boolean/null-like string identity key -> exact string lookup ----------
def test_Q_boolean_like_key():
    m = _mapping({"true": {"person_uuid": "u", "display_name": "Yes Person",
                           "relationship": "Friend", "enabled": True}})
    pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                 "sub_label": "true", "sub_label_score": 0.9})
    r = normalize_identity(pe, m)
    assert r.outcome == Outcome.IDENTITY_KNOWN and r.identity == "Yes Person"


# R. Unicode identity/display name preserved -------------------------------
def test_R_unicode():
    m = _mapping({"José": {"person_uuid": "u", "display_name": "José Árbol",
                          "relationship": "Family", "enabled": True}})
    pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                 "sub_label": "José", "sub_label_score": 0.9})
    r = normalize_identity(pe, m)
    assert r.outcome == Outcome.IDENTITY_KNOWN and r.identity == "José Árbol"


# S. sequential event isolation (no stale leakage) -------------------------
def test_S_sequential_isolation():
    m = _mapping(_KNOWN_ENTRY)
    known = normalize_identity(_parse({"id": "1", "camera": "front_door", "label": "person",
                                       "sub_label": "Known_Person_A", "sub_label_score": 0.93, "score": 0.84}), m)
    unknown = normalize_identity(_parse({"id": "2", "camera": "front_door", "label": "person",
                                         "sub_label": None, "score": 0.7}), m)
    assert known.identity == "Known Person A"
    # the second result carries nothing from the first
    assert unknown.identity is None and unknown.person_uuid is None and unknown.relationship is None
    assert unknown.recognition_confidence is None


# T. malformed identity entry object (not a dict) -> MAPPING_UNAVAILABLE ----
def test_T_malformed_entry_object():
    m = _mapping({"X": "not-an-object"})
    pe = _parse({"id": "e", "camera": "front_door", "label": "person", "sub_label": "X", "sub_label_score": 0.9})
    assert normalize_identity(pe, m).outcome == Outcome.MAPPING_UNAVAILABLE


# U. schema_version bool true -> rejected ----------------------------------
def test_U_schema_bool_rejected():
    pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                 "sub_label": "Known_Person_A", "sub_label_score": 0.9})
    r = normalize_identity(pe, {"schema_version": True, "identities": _KNOWN_ENTRY})
    assert r.outcome == Outcome.MAPPING_UNAVAILABLE


# V. disabled entry with malformed metadata -> still DISABLED, trusted null -
def test_V_disabled_malformed_metadata():
    m = _mapping({"X": {"relationship": "BFF", "enabled": False}})  # bad relationship, no uuid/name
    pe = _parse({"id": "e", "camera": "front_door", "label": "person",
                 "sub_label": "X", "sub_label_score": 0.9, "score": 0.8})
    r = normalize_identity(pe, m)
    assert r.outcome == Outcome.IDENTITY_DISABLED and r.known is False
    assert r.identity is None and r.person_uuid is None and r.relationship is None
    assert r.enabled is False


# Result immutability sanity ------------------------------------------------
def test_result_is_frozen():
    import dataclasses, pytest
    r = normalize_identity(_parse({"id": "e", "camera": "front_door", "label": "person",
                                   "sub_label": None}), _mapping(_KNOWN_ENTRY))
    assert isinstance(r, IdentityNormalizationResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.known = True  # type: ignore[misc]


def test_allowed_relationships_constant():
    assert ALLOWED_RELATIONSHIPS == ("Family", "Friend", "Neighbor", "Other Known")
