"""Identity normalization — pure reference model (Feature 001, T034-C2.1).

PURE REFERENCE / TEST LIBRARY ONLY. This is the contract oracle for the HA-side Jinja
normalization (T034-C2.2+). It does NOT run as a service:
  - no MQTT / no HA / no Frigate / no enrollment DB / no network
  - no filesystem runtime-mapping loading (callers supply the already-loaded mapping)
  - no daemon / no __main__ entry point / no runtime state

It consumes the T034-A ``FrigateEventParse`` (raw event parsing stays in T034-A) plus an
already-loaded relationship mapping and an explicit ``mapping_status``, and returns a
deterministic ``IdentityNormalizationResult``.

Locked rules (T034-C2.1):
  - known=true ONLY for a fully-valid IDENTITY_KNOWN (see TRUST RULE / precedence below).
  - Missing/invalid recognition score with an asserted identity => RECOGNITION_FAILURE
    (fail-closed; NEVER substitute after.score/top_score, NEVER invent a confidence).
  - Mapping globally unavailable/invalid => MAPPING_UNAVAILABLE.
  - Identity ABSENT from a valid mapping => IDENTITY_UNMAPPED.
  - Identity entry present but BROKEN (enabled!=bool, or enabled=true with invalid
    relationship/uuid/display_name) => MAPPING_UNAVAILABLE.
  - Entry present, mapping, enabled exactly False => IDENTITY_DISABLED (public trusted
    metadata stays null regardless of other field validity).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from bridge.frigate_event_parser import FrigateEventParse, ParseOutcome

# Allowed relationship categories (must match the enrollment app / mapping contract).
ALLOWED_RELATIONSHIPS = ("Family", "Friend", "Neighbor", "Other Known")

# Supported mapping schema version (integer, exactly 1).
SUPPORTED_SCHEMA_VERSION = 1


class Outcome:
    """Normalized outcome constants (string values for stable serialization)."""

    IDENTITY_KNOWN = "IDENTITY_KNOWN"
    IDENTITY_UNKNOWN = "IDENTITY_UNKNOWN"
    IDENTITY_DISABLED = "IDENTITY_DISABLED"
    IDENTITY_UNMAPPED = "IDENTITY_UNMAPPED"
    MAPPING_UNAVAILABLE = "MAPPING_UNAVAILABLE"
    RECOGNITION_FAILURE = "RECOGNITION_FAILURE"
    IGNORED_NON_PERSON = "IGNORED_NON_PERSON"


class MappingStatus:
    """Explicit mapping-availability signal supplied by the caller (never inferred by
    Jinja exceptions)."""

    LOADED = "LOADED"          # a mapping object is provided; validate it here
    MISSING = "MISSING"        # no mapping available at all
    MALFORMED = "MALFORMED"    # loader could not parse the mapping file
    UNSUPPORTED = "UNSUPPORTED"  # loader flagged an unsupported schema


@dataclass(frozen=True)
class IdentityNormalizationResult:
    outcome: str
    known: bool
    raw_identity: str | None
    identity: str | None
    person_uuid: str | None
    relationship: str | None
    enabled: bool | None
    recognition_confidence: float | None
    detection_confidence: float | None
    reason: str | None = None


def _valid_score(value: Any) -> bool:
    """A recognition/detection score is valid iff it's a finite real number and NOT a bool
    (bool is an int subclass in Python and must be rejected). NaN/inf are invalid."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return False


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def normalize_identity(
    parsed_event: FrigateEventParse,
    relationship_mapping: Any = None,
    mapping_status: str = MappingStatus.LOADED,
) -> IdentityNormalizationResult:
    """Deterministically normalize a parsed Frigate event against a relationship mapping.

    ``parsed_event`` is a T034-A FrigateEventParse. ``relationship_mapping`` is the
    already-loaded mapping object (or None). ``mapping_status`` is the caller's explicit
    availability signal. Never raises; never mutates; pure.
    """
    detection = parsed_event.detection_score if _valid_score(parsed_event.detection_score) else None

    def result(outcome, *, known=False, raw_identity=None, identity=None, person_uuid=None,
               relationship=None, enabled=None, recognition_confidence=None,
               detection_confidence=detection, reason=None):
        return IdentityNormalizationResult(
            outcome=outcome, known=known, raw_identity=raw_identity, identity=identity,
            person_uuid=person_uuid, relationship=relationship, enabled=enabled,
            recognition_confidence=recognition_confidence,
            detection_confidence=detection_confidence, reason=reason,
        )

    # (1) non-person / parse error from T034-A
    if parsed_event.outcome is ParseOutcome.IGNORED_NON_PERSON:
        return result(Outcome.IGNORED_NON_PERSON, reason="non-person event")
    if parsed_event.outcome is ParseOutcome.PARSE_ERROR:
        # Malformed raw event that prevented safe interpretation.
        return result(Outcome.RECOGNITION_FAILURE, reason="parse error", detection_confidence=None)

    # From here: a PERSON_EVENT.
    # (2) malformed identity flagged by the parser (e.g. sub_label was a list/dict/number):
    #     parser records an error and never sets an identity.
    if parsed_event.error and not parsed_event.has_recognized_identity:
        return result(Outcome.RECOGNITION_FAILURE, reason="malformed sub_label")

    # (3) no asserted identity -> Unknown (empty/whitespace/null sub_label folds here).
    if not parsed_event.has_recognized_identity:
        return result(Outcome.IDENTITY_UNKNOWN)

    raw_identity = parsed_event.sub_label  # non-empty scalar string (parser guaranteed)

    # (4) asserted identity but missing/invalid recognition score -> fail-closed.
    if not _valid_score(parsed_event.sub_label_score):
        return result(
            Outcome.RECOGNITION_FAILURE,
            raw_identity=raw_identity,
            reason="recognized identity without valid recognition confidence",
        )
    recognition = float(parsed_event.sub_label_score)

    # (5) mapping globally unavailable/invalid -> MAPPING_UNAVAILABLE.
    if mapping_status != MappingStatus.LOADED:
        return result(Outcome.MAPPING_UNAVAILABLE, raw_identity=raw_identity,
                      recognition_confidence=recognition, reason=f"mapping {mapping_status.lower()}")
    if not isinstance(relationship_mapping, dict):
        return result(Outcome.MAPPING_UNAVAILABLE, raw_identity=raw_identity,
                      recognition_confidence=recognition, reason="mapping is not an object")
    schema = relationship_mapping.get("schema_version")
    if isinstance(schema, bool) or schema != SUPPORTED_SCHEMA_VERSION or not isinstance(schema, int):
        return result(Outcome.MAPPING_UNAVAILABLE, raw_identity=raw_identity,
                      recognition_confidence=recognition, reason="unsupported/invalid schema_version")
    identities = relationship_mapping.get("identities")
    if not isinstance(identities, dict):
        return result(Outcome.MAPPING_UNAVAILABLE, raw_identity=raw_identity,
                      recognition_confidence=recognition, reason="identities is not an object")

    # (6) identity absent from a valid mapping -> UNMAPPED.
    if raw_identity not in identities:
        return result(Outcome.IDENTITY_UNMAPPED, raw_identity=raw_identity,
                      recognition_confidence=recognition, reason="identity not in mapping")

    entry = identities[raw_identity]

    # (7) matching entry malformed -> MAPPING_UNAVAILABLE (broken != absent).
    if not isinstance(entry, dict):
        return result(Outcome.MAPPING_UNAVAILABLE, raw_identity=raw_identity,
                      recognition_confidence=recognition, reason="identity entry is not an object")
    enabled = entry.get("enabled")
    if not isinstance(enabled, bool):
        return result(Outcome.MAPPING_UNAVAILABLE, raw_identity=raw_identity,
                      recognition_confidence=recognition, reason="entry.enabled is not a boolean")

    # (8) enabled exactly False -> DISABLED, regardless of other field validity.
    #     Public trusted metadata stays null.
    if enabled is False:
        return result(Outcome.IDENTITY_DISABLED, raw_identity=raw_identity, enabled=False,
                      recognition_confidence=recognition, reason="identity explicitly disabled")

    # enabled is True -> validate trusted fields before allowing known.
    person_uuid = entry.get("person_uuid")
    display_name = entry.get("display_name")
    relationship = entry.get("relationship")
    if not _nonempty_str(person_uuid):
        return result(Outcome.MAPPING_UNAVAILABLE, raw_identity=raw_identity,
                      recognition_confidence=recognition, reason="entry.person_uuid invalid")
    if not _nonempty_str(display_name):
        return result(Outcome.MAPPING_UNAVAILABLE, raw_identity=raw_identity,
                      recognition_confidence=recognition, reason="entry.display_name invalid")
    if relationship not in ALLOWED_RELATIONSHIPS:
        return result(Outcome.MAPPING_UNAVAILABLE, raw_identity=raw_identity,
                      recognition_confidence=recognition, reason="entry.relationship invalid")

    # (9) fully valid -> KNOWN.
    return result(
        Outcome.IDENTITY_KNOWN,
        known=True,
        raw_identity=raw_identity,
        identity=display_name,
        person_uuid=person_uuid,
        relationship=relationship,
        enabled=True,
        recognition_confidence=recognition,
    )
