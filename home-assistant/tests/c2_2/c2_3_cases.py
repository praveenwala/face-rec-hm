"""T034-C2.3 — single canonical synthetic case matrix (parity source of truth).

ONE authoritative case table consumed by BOTH parity paths:
  - Python oracle path : raw event -> T034-A parse_event() -> normalize_identity()
  - HA/Jinja path      : same raw event -> C2.2 macro normalize(ev, mapping, status)

No normalization rules are re-implemented here; this file only supplies inputs (and a
human-readable category for reporting). Synthetic identities only.

Each case:
  id            : stable case id (A..AM + variants)
  event         : raw frigate/events-style payload ({type, before, after}) OR None
  mapping_key   : which shared mapping variant to use ("base" | "missing" | "schema2"
                  | "no_schema" | "no_identities" | "not_a_dict")
  category      : coarse semantic bucket for the report (not asserted; outcome is)

Score edge cases that JSON cannot represent (NaN/inf) are handled separately by the
harness at the real ingestion boundary (see c2_3_score_boundary in the test), because a
raw MQTT JSON payload can never carry NaN/inf; representing them would fabricate a path
that does not exist at runtime.
"""
from __future__ import annotations

# ---- shared synthetic relationship mapping (base) — mirrors C1 schema exactly ----
BASE_MAPPING = {
    "schema_version": 1,
    "identities": {
        "Known_Person_A": {
            "person_uuid": "00000000-0000-0000-0000-00000000000a",
            "display_name": "Known Person A",
            "relationship": "Family",
            "enabled": True,
        },
        "Known_Person_B": {
            "person_uuid": "00000000-0000-0000-0000-00000000000b",
            "display_name": "Known Person B",
            "relationship": "Friend",
            "enabled": True,
        },
        "Disabled_Person": {
            "person_uuid": "00000000-0000-0000-0000-0000000000d1",
            "display_name": "Disabled Person",
            "relationship": "Neighbor",
            "enabled": False,
        },
        "José": {
            "person_uuid": "00000000-0000-0000-0000-0000000000c3",
            "display_name": "José Árbol",
            "relationship": "Friend",
            "enabled": True,
        },
        "true": {
            "person_uuid": "00000000-0000-0000-0000-00000000c0de",
            "display_name": "Yes Person",
            "relationship": "Other Known",
            "enabled": True,
        },
        "null": {
            "person_uuid": "00000000-0000-0000-0000-00000000nu11",
            "display_name": "Null Key Person",
            "relationship": "Family",
            "enabled": True,
        },
        "123": {
            "person_uuid": "00000000-0000-0000-0000-000000000123",
            "display_name": "Numeric Key Person",
            "relationship": "Family",
            "enabled": True,
        },
        # broken (present but malformed) entries -> MAPPING_UNAVAILABLE
        "Bad_Relationship": {
            "person_uuid": "00000000-0000-0000-0000-0000000badre",
            "display_name": "Bad Rel",
            "relationship": "BFF",
            "enabled": True,
        },
        "Wrong_Enabled_Type": {
            "person_uuid": "00000000-0000-0000-0000-000000wrongt",
            "display_name": "Wrong Enabled",
            "relationship": "Family",
            "enabled": "true",
        },
        "Missing_UUID": {
            "display_name": "No UUID",
            "relationship": "Family",
            "enabled": True,
        },
        "Empty_UUID": {
            "person_uuid": "   ",
            "display_name": "Empty UUID",
            "relationship": "Family",
            "enabled": True,
        },
        "Missing_Display_Name": {
            "person_uuid": "00000000-0000-0000-0000-000000nodn01",
            "relationship": "Family",
            "enabled": True,
        },
        "Empty_Display_Name": {
            "person_uuid": "00000000-0000-0000-0000-000000edn001",
            "display_name": "   ",
            "relationship": "Family",
            "enabled": True,
        },
        "Entry_Not_Object": "just-a-string",
        # disabled entries with malformed OTHER metadata -> still IDENTITY_DISABLED
        "Disabled_Bad_Rel": {
            "person_uuid": "00000000-0000-0000-0000-0000000dbr01",
            "display_name": "Disabled Bad Rel",
            "relationship": "BFF",
            "enabled": False,
        },
        "Disabled_Missing_UUID": {
            "display_name": "Disabled No UUID",
            "relationship": "Neighbor",
            "enabled": False,
        },
        "Disabled_Missing_DN": {
            "person_uuid": "00000000-0000-0000-0000-0000000dmd01",
            "relationship": "Neighbor",
            "enabled": False,
        },
    },
}

# Mapping variants for the "globally invalid/unavailable" cases.
_SCHEMA2 = {**BASE_MAPPING, "schema_version": 2}
_NO_SCHEMA = {"identities": BASE_MAPPING["identities"]}
_NO_IDENTITIES = {"schema_version": 1}
_NOT_A_DICT = ["not", "a", "dict"]

MAPPINGS = {
    "base": BASE_MAPPING,
    "missing": None,          # paired with mapping_status=MISSING
    "schema2": _SCHEMA2,
    "no_schema": _NO_SCHEMA,
    "no_identities": _NO_IDENTITIES,
    "not_a_dict": _NOT_A_DICT,
}
# mapping_status per variant (LOADED unless the variant models an unavailable mapping)
MAPPING_STATUS = {
    "base": "LOADED",
    "missing": "MISSING",
    "schema2": "LOADED",
    "no_schema": "LOADED",
    "no_identities": "LOADED",
    "not_a_dict": "LOADED",
}


def _person(after: dict, type_: str = "update") -> dict:
    return {"type": type_, "before": {}, "after": after}


# ---- canonical case matrix ------------------------------------------------
CASES = [
    # A. known enabled
    {"id": "A_known_enabled", "category": "known", "mapping_key": "base",
     "event": _person({"id": "A", "camera": "front_door", "label": "person",
                       "sub_label": "Known_Person_A", "sub_label_score": 0.93, "score": 0.84})},
    # B. unknown null identity
    {"id": "B_unknown_null", "category": "unknown", "mapping_key": "base",
     "event": _person({"id": "B", "camera": "front_door", "label": "person",
                       "sub_label": None, "score": 0.80})},
    # C. disabled identity
    {"id": "C_disabled", "category": "disabled", "mapping_key": "base",
     "event": _person({"id": "C", "camera": "front_door", "label": "person",
                       "sub_label": "Disabled_Person", "sub_label_score": 0.95, "score": 0.82})},
    # D. unmapped identity
    {"id": "D_unmapped", "category": "unmapped", "mapping_key": "base",
     "event": _person({"id": "D", "camera": "front_door", "label": "person",
                       "sub_label": "Nobody", "sub_label_score": 0.90, "score": 0.80})},
    # E. invalid relationship (enabled entry)
    {"id": "E_invalid_relationship", "category": "mapping_unavailable", "mapping_key": "base",
     "event": _person({"id": "E", "camera": "front_door", "label": "person",
                       "sub_label": "Bad_Relationship", "sub_label_score": 0.90})},
    # F. mapping missing
    {"id": "F_mapping_missing", "category": "mapping_unavailable", "mapping_key": "missing",
     "event": _person({"id": "F", "camera": "front_door", "label": "person",
                       "sub_label": "Known_Person_A", "sub_label_score": 0.90})},
    # G. mapping wrong type
    {"id": "G_mapping_wrong_type", "category": "mapping_unavailable", "mapping_key": "not_a_dict",
     "event": _person({"id": "G", "camera": "front_door", "label": "person",
                       "sub_label": "Known_Person_A", "sub_label_score": 0.90})},
    # H. schema version missing
    {"id": "H_schema_missing", "category": "mapping_unavailable", "mapping_key": "no_schema",
     "event": _person({"id": "H", "camera": "front_door", "label": "person",
                       "sub_label": "Known_Person_A", "sub_label_score": 0.90})},
    # I. unsupported schema version
    {"id": "I_unsupported_schema", "category": "mapping_unavailable", "mapping_key": "schema2",
     "event": _person({"id": "I", "camera": "front_door", "label": "person",
                       "sub_label": "Known_Person_A", "sub_label_score": 0.90})},
    # J. identities missing
    {"id": "J_identities_missing", "category": "mapping_unavailable", "mapping_key": "no_identities",
     "event": _person({"id": "J", "camera": "front_door", "label": "person",
                       "sub_label": "Known_Person_A", "sub_label_score": 0.90})},
    # K. identity entry wrong type
    {"id": "K_entry_wrong_type", "category": "mapping_unavailable", "mapping_key": "base",
     "event": _person({"id": "K", "camera": "front_door", "label": "person",
                       "sub_label": "Entry_Not_Object", "sub_label_score": 0.90})},
    # L. malformed sub_label list
    {"id": "L_malformed_list", "category": "recognition_failure", "mapping_key": "base",
     "event": _person({"id": "L", "camera": "front_door", "label": "person",
                       "sub_label": ["Known_Person_A", 0.9], "sub_label_score": 0.9, "score": 0.80})},
    # M. malformed sub_label dict
    {"id": "M_malformed_dict", "category": "recognition_failure", "mapping_key": "base",
     "event": _person({"id": "M", "camera": "front_door", "label": "person",
                       "sub_label": {"n": "x"}, "sub_label_score": 0.9, "score": 0.80})},
    # N. malformed sub_label number
    {"id": "N_malformed_number", "category": "recognition_failure", "mapping_key": "base",
     "event": _person({"id": "N", "camera": "front_door", "label": "person",
                       "sub_label": 123, "sub_label_score": 0.9, "score": 0.80})},
    # O. empty sub_label
    {"id": "O_empty_sub_label", "category": "unknown", "mapping_key": "base",
     "event": _person({"id": "O", "camera": "front_door", "label": "person",
                       "sub_label": "", "score": 0.80})},
    # P. whitespace-only sub_label
    {"id": "P_whitespace_sub_label", "category": "unknown", "mapping_key": "base",
     "event": _person({"id": "P", "camera": "front_door", "label": "person",
                       "sub_label": "   ", "score": 0.80})},
    # Q. valid recognition/detection score separation
    {"id": "Q_score_separation", "category": "known", "mapping_key": "base",
     "event": _person({"id": "Q", "camera": "front_door", "label": "person",
                       "sub_label": "Known_Person_A", "sub_label_score": 0.93, "score": 0.84})},
    # R. missing recognition score
    {"id": "R_missing_recognition_score", "category": "recognition_failure", "mapping_key": "base",
     "event": _person({"id": "R", "camera": "front_door", "label": "person",
                       "sub_label": "Known_Person_A", "score": 0.84})},
    # S. recognition score bool true
    {"id": "S_score_bool_true", "category": "recognition_failure", "mapping_key": "base",
     "event": _person({"id": "S", "camera": "front_door", "label": "person",
                       "sub_label": "Known_Person_A", "sub_label_score": True, "score": 0.80})},
    # T. recognition score bool false
    {"id": "T_score_bool_false", "category": "recognition_failure", "mapping_key": "base",
     "event": _person({"id": "T", "camera": "front_door", "label": "person",
                       "sub_label": "Known_Person_A", "sub_label_score": False, "score": 0.80})},
    # U/V (NaN/inf) handled by the score-boundary test, not here (JSON cannot carry them).
    # W. non-person event
    {"id": "W_non_person", "category": "ignored", "mapping_key": "base",
     "event": _person({"id": "W", "camera": "front_door", "label": "car",
                       "sub_label": "whatever", "score": 0.80})},
    # X. enabled wrong type
    {"id": "X_enabled_wrong_type", "category": "mapping_unavailable", "mapping_key": "base",
     "event": _person({"id": "X", "camera": "front_door", "label": "person",
                       "sub_label": "Wrong_Enabled_Type", "sub_label_score": 0.90})},
    # Y. missing UUID
    {"id": "Y_missing_uuid", "category": "mapping_unavailable", "mapping_key": "base",
     "event": _person({"id": "Y", "camera": "front_door", "label": "person",
                       "sub_label": "Missing_UUID", "sub_label_score": 0.90})},
    # Z. empty UUID
    {"id": "Z_empty_uuid", "category": "mapping_unavailable", "mapping_key": "base",
     "event": _person({"id": "Z", "camera": "front_door", "label": "person",
                       "sub_label": "Empty_UUID", "sub_label_score": 0.90})},
    # AA. missing display_name
    {"id": "AA_missing_display_name", "category": "mapping_unavailable", "mapping_key": "base",
     "event": _person({"id": "AA", "camera": "front_door", "label": "person",
                       "sub_label": "Missing_Display_Name", "sub_label_score": 0.90})},
    # AB. empty display_name
    {"id": "AB_empty_display_name", "category": "mapping_unavailable", "mapping_key": "base",
     "event": _person({"id": "AB", "camera": "front_door", "label": "person",
                       "sub_label": "Empty_Display_Name", "sub_label_score": 0.90})},
    # AC. boolean-looking identity key "true"
    {"id": "AC_key_true", "category": "known", "mapping_key": "base",
     "event": _person({"id": "AC", "camera": "front_door", "label": "person",
                       "sub_label": "true", "sub_label_score": 0.90})},
    # AD. null-looking identity key "null"
    {"id": "AD_key_null", "category": "known", "mapping_key": "base",
     "event": _person({"id": "AD", "camera": "front_door", "label": "person",
                       "sub_label": "null", "sub_label_score": 0.90})},
    # AE. numeric-looking identity key "123"
    {"id": "AE_key_123", "category": "known", "mapping_key": "base",
     "event": _person({"id": "AE", "camera": "front_door", "label": "person",
                       "sub_label": "123", "sub_label_score": 0.90})},
    # AF. Unicode identity/display_name
    {"id": "AF_unicode", "category": "known", "mapping_key": "base",
     "event": _person({"id": "AF", "camera": "front_door", "label": "person",
                       "sub_label": "José", "sub_label_score": 0.90})},
    # AG. disabled entry with malformed relationship
    {"id": "AG_disabled_bad_rel", "category": "disabled", "mapping_key": "base",
     "event": _person({"id": "AG", "camera": "front_door", "label": "person",
                       "sub_label": "Disabled_Bad_Rel", "sub_label_score": 0.90, "score": 0.80})},
    # AH. disabled entry with missing UUID
    {"id": "AH_disabled_missing_uuid", "category": "disabled", "mapping_key": "base",
     "event": _person({"id": "AH", "camera": "front_door", "label": "person",
                       "sub_label": "Disabled_Missing_UUID", "sub_label_score": 0.90, "score": 0.80})},
    # AI. disabled entry with missing display_name
    {"id": "AI_disabled_missing_dn", "category": "disabled", "mapping_key": "base",
     "event": _person({"id": "AI", "camera": "front_door", "label": "person",
                       "sub_label": "Disabled_Missing_DN", "sub_label_score": 0.90, "score": 0.80})},
    # AM. absent vs broken distinction (absent side; broken side is E/K/X above)
    {"id": "AM_absent_entry", "category": "unmapped", "mapping_key": "base",
     "event": _person({"id": "AM", "camera": "front_door", "label": "person",
                       "sub_label": "Totally_Absent", "sub_label_score": 0.90, "score": 0.80})},
]

# Sequential isolation sequences (AJ, AK, AL, + DISABLED->UNMAPPED). Each sequence is a
# list of raw events rendered in order within ONE harness/process; only the base mapping.
SEQUENCES = {
    "AJ_known_to_unknown": [
        _person({"id": "s1", "camera": "front_door", "label": "person",
                 "sub_label": "Known_Person_A", "sub_label_score": 0.93, "score": 0.84}),
        _person({"id": "s2", "camera": "front_door", "label": "person",
                 "sub_label": None, "score": 0.70}),
    ],
    "AK_known_a_to_known_b": [
        _person({"id": "s1", "camera": "front_door", "label": "person",
                 "sub_label": "Known_Person_A", "sub_label_score": 0.93, "score": 0.84}),
        _person({"id": "s2", "camera": "front_door", "label": "person",
                 "sub_label": "Known_Person_B", "sub_label_score": 0.88, "score": 0.79}),
    ],
    "AL_failure_to_known": [
        _person({"id": "s1", "camera": "front_door", "label": "person",
                 "sub_label": "Known_Person_A", "score": 0.84}),  # missing recog score -> failure
        _person({"id": "s2", "camera": "front_door", "label": "person",
                 "sub_label": "Known_Person_A", "sub_label_score": 0.93, "score": 0.84}),
    ],
    "disabled_to_unmapped": [
        _person({"id": "s1", "camera": "front_door", "label": "person",
                 "sub_label": "Disabled_Person", "sub_label_score": 0.95, "score": 0.82}),
        _person({"id": "s2", "camera": "front_door", "label": "person",
                 "sub_label": "Nobody", "sub_label_score": 0.90, "score": 0.80}),
    ],
}
