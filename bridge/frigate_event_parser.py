"""Frigate → recognition-pipeline event parser (Feature 001, T034-A).

SCOPE (T034-A only): faithfully parse/normalize the RAW Frigate 0.17.2 MQTT event and
availability payloads. This layer does NOT:
  - enrich relationship (that is T034-B)
  - decide Known/Unknown policy, liveness, or confidence thresholds
  - publish any normalized Home Assistant topic (T034-C)
  - touch Home Assistant, Frigate, or the enrollment DB

It is a pure, dependency-free parsing library (stdlib only) so it can run anywhere and be
unit-tested deterministically. Architecture note: Feature 001's ratified plan puts the
enrichment/dedup/relationship logic in Home Assistant Jinja templates ("no custom bridge
service"); this module is a self-contained parser/validation layer, not a running service —
see the T034-A report for the flagged deviation to confirm before building a live bridge.

CORRECTED Frigate 0.17.2 wire contract (2026-09-17, from a captured live production
positive match — see docs/production/mqtt-b5-production-verification-2026-09-17.md and
the T035 root-cause analysis). The prior "VERIFIED" claim here was wrong for genuine
matches: it was validated only against hand-constructed synthetic fixtures and
null/no-match cases, never a real positive match. `after.sub_label` on `frigate/events`
has TWO observed shapes, both supported:
  - Shape A (scalar): a non-empty identity-name STRING (or null for no identity); the
    FACE-RECOGNITION confidence is the SEPARATE field `after.sub_label_score`.
  - Shape B (legacy array — Frigate 0.17.2's ACTUAL shape for a genuine positive match):
    a 2-element `[name, score]` list. `after.sub_label_score` is NOT emitted in this
    case; the array's second element IS the recognition confidence.
Any other shape (dict, number, bool, wrong-length/typed array) is malformed and must
NEVER be treated as a known identity. `after.score` / `after.top_score` are the
OBJECT/PERSON-DETECTION confidence and MUST NEVER be used as the recognition confidence,
for either shape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ParseOutcome(str, Enum):
    """Explicit result of attempting to parse one raw MQTT message."""

    PERSON_EVENT = "PERSON_EVENT"          # a person tracked-object event, parsed
    IGNORED_NON_PERSON = "IGNORED_NON_PERSON"  # valid event, but label != person
    PARSE_ERROR = "PARSE_ERROR"            # malformed/undecodable — never a person/identity


class Availability(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"  # unrecognized/absent value — treated as not-confirmed-online


@dataclass(frozen=True)
class FrigateEventParse:
    """Result of parsing one `frigate/events` message.

    ``outcome`` is always set. Fields are populated only for PERSON_EVENT. This is a faithful
    representation of the raw Frigate event — no policy, no enrichment.
    """

    outcome: ParseOutcome
    # populated for PERSON_EVENT:
    lifecycle: str | None = None            # "new" | "update" | "end" | other (raw)
    event_id: str | None = None             # after.id — correlation key across new/update/end
    camera: str | None = None               # after.camera
    label: str | None = None                # after.label (e.g. "person")
    start_time: float | None = None
    end_time: float | None = None           # null while ongoing
    # identity (raw, NO policy): scalar identity name string, or None if no recognized identity
    sub_label: str | None = None
    has_recognized_identity: bool = False   # True iff sub_label is a non-empty string
    # confidences — kept STRICTLY separate:
    sub_label_score: float | None = None    # FACE-RECOGNITION confidence (or None if absent)
    detection_score: float | None = None    # after.score — OBJECT/PERSON DETECTION only
    top_score: float | None = None          # after.top_score — detection
    false_positive: bool | None = None
    # diagnostics:
    error: str | None = None                # reason for PARSE_ERROR / non-person note
    raw_after_keys: tuple[str, ...] = field(default_factory=tuple)


def _coerce_float(value: Any) -> float | None:
    """Return a float if value is a real number, else None. Never raises."""
    if isinstance(value, bool):  # bool is an int subclass; reject to avoid True->1.0
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _coerce_identity(sub_label: Any) -> tuple[str | None, float | None, str | None]:
    """Interpret raw sub_label, accepting BOTH supported Frigate 0.17.2 wire shapes.

    Shape A (scalar string): a non-empty identity name; its recognition confidence
    comes separately from `after.sub_label_score` (read by the caller).
    Shape B (legacy 2-element array): `[name, score]` — Frigate 0.17.2's ACTUAL wire
    shape for a genuine positive match (confirmed via a captured live production
    event, 2026-09-17); `after.sub_label_score` is NOT emitted in this case, so the
    array's second element IS the recognition confidence.

    Returns (identity_or_None, array_score_or_None, error_or_None):
      - null/missing sub_label            -> (None, None, None)              no identity
      - non-empty string                  -> (identity, None, None)          Shape A
      - valid 2-elem [name, score] array   -> (identity, score, None)        Shape B
      - anything else (malformed)         -> (None, None, "malformed ...")   fail closed

    The returned Shape-B `score` is the RAW coerced float (may be NaN/inf) — validity
    (finite, non-bool) is enforced uniformly downstream by
    ``identity_normalizer._valid_score`` for BOTH shapes, exactly as it already does for
    Shape A's `sub_label_score`. This function only decides shape well-formedness, never
    score validity — keeping a single source of truth for "is this score acceptable."
    """
    if sub_label is None:
        return None, None, None
    if isinstance(sub_label, str):
        s = sub_label.strip()
        return (s, None, None) if s else (None, None, None)
    if isinstance(sub_label, (list, tuple)) and len(sub_label) == 2:
        name, score = sub_label[0], sub_label[1]
        name_ok = isinstance(name, str) and name.strip() != ""
        score_val = _coerce_float(score)
        if name_ok and score_val is not None:
            return name.strip(), score_val, None
    # Malformed: wrong-length/typed array, dict, number, bool, etc. — fail safe.
    return None, None, f"malformed sub_label (type={type(sub_label).__name__}); treated as no identity"


def parse_event(raw: str | bytes | dict) -> FrigateEventParse:
    """Parse one raw `frigate/events` MQTT message. Never raises; always returns a result.

    Accepts a JSON string/bytes or an already-decoded dict.
    """
    # 1) decode JSON
    if isinstance(raw, (str, bytes)):
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError) as exc:
            return FrigateEventParse(ParseOutcome.PARSE_ERROR, error=f"invalid JSON: {exc}")
    elif isinstance(raw, dict):
        payload = raw
    else:
        return FrigateEventParse(ParseOutcome.PARSE_ERROR, error=f"unsupported input type {type(raw).__name__}")

    if not isinstance(payload, dict):
        return FrigateEventParse(ParseOutcome.PARSE_ERROR, error="top-level payload is not an object")

    lifecycle = payload.get("type")
    after = payload.get("after")
    if not isinstance(after, dict):
        return FrigateEventParse(
            ParseOutcome.PARSE_ERROR,
            lifecycle=lifecycle if isinstance(lifecycle, str) else None,
            error="missing or malformed 'after' object",
        )

    raw_keys = tuple(sorted(k for k in after.keys() if isinstance(k, str)))
    label = after.get("label")

    # 5) person filtering — only person events advance. Non-person is IGNORED, never Unknown-person.
    if label != "person":
        return FrigateEventParse(
            ParseOutcome.IGNORED_NON_PERSON,
            lifecycle=lifecycle if isinstance(lifecycle, str) else None,
            label=label if isinstance(label, str) else None,
            event_id=after.get("id") if isinstance(after.get("id"), str) else None,
            camera=after.get("camera") if isinstance(after.get("camera"), str) else None,
            raw_after_keys=raw_keys,
            error="non-person label ignored" if label is not None else "missing label ignored",
        )

    # A person event. Required-ish fields are parsed defensively (missing => None, not crash).
    event_id = after.get("id") if isinstance(after.get("id"), str) else None
    camera = after.get("camera") if isinstance(after.get("camera"), str) else None

    identity, array_score, id_err = _coerce_identity(after.get("sub_label"))

    # recognition confidence: Shape B's array score takes precedence when present (its
    # after.sub_label_score is never emitted); otherwise Shape A's top-level
    # sub_label_score, then the after.data.sub_label_score fallback. NEVER fall back to
    # detection score.
    if array_score is not None:
        recog = array_score
    else:
        recog = _coerce_float(after.get("sub_label_score"))
        if recog is None:
            data = after.get("data")
            if isinstance(data, dict):
                recog = _coerce_float(data.get("sub_label_score"))

    return FrigateEventParse(
        outcome=ParseOutcome.PERSON_EVENT,
        lifecycle=lifecycle if isinstance(lifecycle, str) else None,
        event_id=event_id,
        camera=camera,
        label="person",
        start_time=_coerce_float(after.get("start_time")),
        end_time=_coerce_float(after.get("end_time")),
        sub_label=identity,
        has_recognized_identity=identity is not None,
        sub_label_score=recog,
        detection_score=_coerce_float(after.get("score")),
        top_score=_coerce_float(after.get("top_score")),
        false_positive=after.get("false_positive") if isinstance(after.get("false_positive"), bool) else None,
        error=id_err,  # malformed sub_label recorded but never becomes an identity
        raw_after_keys=raw_keys,
    )


def parse_availability(raw: str | bytes) -> Availability:
    """Parse a `frigate/available` payload. Recognizes 'online'/'offline'; anything else
    (including undecodable/empty) => UNKNOWN (treated as not-confirmed-online by later
    failure isolation, T034 later phase). Never raises."""
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8", errors="replace")
        except Exception:
            return Availability.UNKNOWN
    if not isinstance(raw, str):
        return Availability.UNKNOWN
    val = raw.strip().strip('"').lower()
    if val == "online":
        return Availability.ONLINE
    if val == "offline":
        return Availability.OFFLINE
    return Availability.UNKNOWN
