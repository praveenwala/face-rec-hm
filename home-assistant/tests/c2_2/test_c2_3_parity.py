"""T034-C2.3 — automated PARITY suite (ISOLATED TEST ONLY).

Proves the Python reference oracle (bridge/identity_normalizer.py, the C2 contract source
of truth) and the C2.2 HA/Jinja fixture (custom_templates/identity_normalization.jinja) produce
SEMANTICALLY IDENTICAL normalized results for one canonical synthetic case matrix
(c2_3_cases.py). The Jinja is exercised through the REAL Home Assistant Template engine —
NOT a generic Jinja2 renderer, and NOT a re-implemented copy of the rules.

Both paths start from the SAME raw frigate/events payload:
  Python : raw -> T034-A parse_event() -> normalize_identity()
  HA     : raw -> C2.2 macro normalize(ev, mapping, mapping_status)

All 10 fields compared EXACTLY (reason strings included — they match verbatim, so parity
strategy = exact reason match; no reason_code needed). Only representation-level
normalization (JSON null == Python None, int/float equality) is applied; no semantic
difference is normalized away.

Isolation: no live HA / MQTT / Frigate / Ring / DB / network. Requires the throwaway HA
venv created by the C2.2 setup (see README). Run with:
    source .ha-venv/bin/activate && python -m pytest test_c2_3_parity.py -v
"""
from __future__ import annotations

import asyncio
import json
import math
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
MACRO = HERE / "custom_templates" / "identity_normalization.jinja"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(HERE))

from bridge.frigate_event_parser import parse_event, FrigateEventParse, ParseOutcome  # noqa: E402
from bridge.identity_normalizer import normalize_identity, MappingStatus  # noqa: E402
import c2_3_cases as cases  # noqa: E402

FIELDS = [
    "outcome", "known", "raw_identity", "identity", "person_uuid",
    "relationship", "enabled", "recognition_confidence", "detection_confidence", "reason",
]

_MACRO_BODY = MACRO.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- oracle
def _oracle(ev, mapping, status) -> dict:
    parsed = parse_event(ev)
    r = normalize_identity(parsed, mapping, status)
    return {f: getattr(r, f) for f in FIELDS}


def _oracle_from_parse(parsed: FrigateEventParse, mapping, status) -> dict:
    r = normalize_identity(parsed, mapping, status)
    return {f: getattr(r, f) for f in FIELDS}


# --------------------------------------------------------------------------- HA render
class _HARenderer:
    """Owns one real HomeAssistant instance + event loop for the whole session."""

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        from homeassistant.core import HomeAssistant
        self._hass = self._loop.run_until_complete(self._make(HomeAssistant))

    async def _make(self, HomeAssistant):
        return HomeAssistant(str(HERE))

    def render(self, ev, mapping, status) -> dict:
        from homeassistant.helpers.template import Template
        tpl = Template(_MACRO_BODY + "\n{{- normalize(ev, mapping, mapping_status) -}}", self._hass)
        out = tpl.async_render(
            {"ev": ev, "mapping": mapping, "mapping_status": status}, parse_result=False
        )
        return json.loads(out)

    def close(self):
        self._loop.run_until_complete(self._hass.async_stop(force=True))
        self._loop.close()


@pytest.fixture(scope="module")
def ha():
    r = _HARenderer()
    yield r
    r.close()


# --------------------------------------------------------------------------- compare
def _norm(v):
    # representation-only normalization; never collapses semantic differences
    return v


def diff_fields(py: dict, hj: dict) -> list[str]:
    diffs = []
    for f in FIELDS:
        a, b = py.get(f), hj.get(f)
        num = (isinstance(a, (int, float)) and not isinstance(a, bool)
               and isinstance(b, (int, float)) and not isinstance(b, bool))
        if num:
            if not (math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-9)):
                diffs.append(f"{f}: python={a!r} ha={b!r}")
        elif a != b:
            diffs.append(f"{f}: python={a!r} ha={b!r}")
    return diffs


def _mapping_for(case):
    key = case["mapping_key"]
    mapping = cases.MAPPINGS[key]
    status = cases.MAPPING_STATUS[key]
    # deep copy loaded dict mappings so per-case renders never share mutable state
    if isinstance(mapping, dict):
        mapping = json.loads(json.dumps(mapping))
    elif isinstance(mapping, list):
        mapping = list(mapping)
    return mapping, status


# --------------------------------------------------------------------------- matrix test
@pytest.mark.parametrize("case", cases.CASES, ids=[c["id"] for c in cases.CASES])
def test_parity_matrix(ha, case):
    mapping, status = _mapping_for(case)
    py = _oracle(case["event"], mapping, status)
    hj = ha.render(case["event"], mapping, status)
    diffs = diff_fields(py, hj)
    assert not diffs, (
        f"\nPARITY MISMATCH [{case['id']}] (category={case['category']})\n"
        f"  python: {py}\n  ha    : {hj}\n  diffs : {diffs}"
    )


# --------------------------------------------------------------------------- score boundary
def test_score_boundary_nan_inf(ha):
    """U/V: NaN/inf recognition scores. JSON (the real MQTT boundary) CANNOT carry NaN/inf,
    so the HA/Jinja runtime can never receive them from a real event — documented limitation.
    We therefore prove:
      (1) the Python oracle fails closed on NaN/inf (constructed FrigateEventParse), and
      (2) at the real HA ingestion boundary, an out-of-range/invalid score string like
          'NaN'/'Infinity' is NOT accepted as a valid number and fails closed identically.
    """
    base = json.loads(json.dumps(cases.BASE_MAPPING))
    # (1) oracle: NaN / +inf / -inf via direct parse object -> RECOGNITION_FAILURE
    for bad in (math.nan, math.inf, -math.inf):
        parsed = FrigateEventParse(
            outcome=ParseOutcome.PERSON_EVENT, label="person", sub_label="Known_Person_A",
            has_recognized_identity=True, sub_label_score=bad, detection_score=0.8,
        )
        r = _oracle_from_parse(parsed, base, MappingStatus.LOADED)
        assert r["outcome"] == "RECOGNITION_FAILURE" and r["recognition_confidence"] is None

    # (2) HA boundary: a JSON string that looks like NaN/Infinity is a STRING, not a number.
    #     Both sides must reject it (not a valid numeric score) -> RECOGNITION_FAILURE.
    for token in ("NaN", "Infinity", "-Infinity"):
        ev = {"type": "update", "before": {}, "after": {
            "id": "nan", "camera": "front_door", "label": "person",
            "sub_label": "Known_Person_A", "sub_label_score": token, "score": 0.8}}
        py = _oracle(ev, base, MappingStatus.LOADED)
        hj = ha.render(ev, base, MappingStatus.LOADED)
        assert py["outcome"] == "RECOGNITION_FAILURE", f"oracle accepted {token!r}"
        assert not diff_fields(py, hj), f"NaN-token parity mismatch for {token!r}: {diff_fields(py, hj)}"


# --------------------------------------------------------------------------- sequential isolation
@pytest.mark.parametrize("seq_name", list(cases.SEQUENCES.keys()))
def test_sequential_isolation(ha, seq_name):
    """Render a sequence of events in ONE process; prove per-event parity AND no stale
    metadata leaking from one render into the next (both implementations)."""
    base = json.loads(json.dumps(cases.BASE_MAPPING))
    events = cases.SEQUENCES[seq_name]
    py_results, ha_results = [], []
    for ev in events:
        py = _oracle(ev, base, MappingStatus.LOADED)
        hj = ha.render(ev, base, MappingStatus.LOADED)
        assert not diff_fields(py, hj), f"[{seq_name}] step parity mismatch: {diff_fields(py, hj)}"
        py_results.append(py)
        ha_results.append(hj)

    # second result must not carry STALE metadata from the first render. The correct
    # expectation is per-sequence (this asserts the *semantics*, and per-step parity above
    # already proved Python==HA for every step):
    first, second = ha_results[0], ha_results[1]
    if seq_name == "AK_known_a_to_known_b":
        # A -> B: second is a legitimate KNOWN B; must be B's metadata only, never A's.
        assert second["identity"] == "Known Person B" and second["person_uuid"].endswith("00000b")
        assert second["identity"] != first["identity"] and second["person_uuid"] != first["person_uuid"]
    elif seq_name == "AL_failure_to_known":
        # FAILURE -> KNOWN A: first is RECOGNITION_FAILURE (no trusted metadata); second is a
        # legitimate KNOWN A. Prove the failure left NO leftovers and the known is complete.
        assert first["outcome"] == "RECOGNITION_FAILURE"
        assert first["identity"] is None and first["person_uuid"] is None and first["recognition_confidence"] is None
        assert second["outcome"] == "IDENTITY_KNOWN" and second["known"] is True
        assert second["identity"] == "Known Person A"
        assert second["person_uuid"].endswith("00000a") and second["recognition_confidence"] == 0.93
    else:
        # AJ (KNOWN A -> UNKNOWN) and disabled_to_unmapped: second transitions AWAY from a
        # trusted known; trusted fields must be cleared (no stale A/disabled leakage).
        assert second["identity"] is None and second["person_uuid"] is None
        assert second["relationship"] is None
    # a following non-recognition/unknown must not inherit the earlier recognition score
    if seq_name in ("AJ_known_to_unknown",):
        assert second["recognition_confidence"] is None
    if seq_name == "disabled_to_unmapped":
        # no 'disabled' flag leakage: second (unmapped) must have enabled=None, not False
        assert second["enabled"] is None


# --------------------------------------------------------------------------- explicit invariants
def test_score_separation_distinct(ha):
    base = json.loads(json.dumps(cases.BASE_MAPPING))
    ev = {"type": "update", "before": {}, "after": {
        "id": "sep", "camera": "front_door", "label": "person",
        "sub_label": "Known_Person_A", "sub_label_score": 0.93, "score": 0.84}}
    py = _oracle(ev, base, MappingStatus.LOADED)
    hj = ha.render(ev, base, MappingStatus.LOADED)
    assert py["recognition_confidence"] == 0.93 and py["detection_confidence"] == 0.84
    assert not diff_fields(py, hj)
    assert hj["recognition_confidence"] != hj["detection_confidence"]


def test_missing_score_no_substitution(ha):
    base = json.loads(json.dumps(cases.BASE_MAPPING))
    ev = {"type": "update", "before": {}, "after": {
        "id": "nosub", "camera": "front_door", "label": "person",
        "sub_label": "Known_Person_A", "score": 0.84}}  # no sub_label_score
    py = _oracle(ev, base, MappingStatus.LOADED)
    hj = ha.render(ev, base, MappingStatus.LOADED)
    assert py["outcome"] == "RECOGNITION_FAILURE"
    assert py["recognition_confidence"] is None and py["detection_confidence"] == 0.84
    assert not diff_fields(py, hj)  # HA never substitutes detection for recognition either


def test_runtime_automation_contract():
    """The isolated runtime fixture only accepts final person events and deduplicates by ID."""
    automation = (HERE / "automations.yaml").read_text(encoding="utf-8")
    assert "topic: frigate/events" in automation
    assert "== 'end'" in automation
    assert "== 'person'" in automation
    assert "input_text.frigate_last_processed_event_id" in automation
    assert "!= trigger.payload_json.after.id" in automation
    assert "event_id: \"{{ trigger.payload_json.after.id }}\"" in automation
    for field in FIELDS:
        assert f"{field}:" in automation


def test_end_person_unknown_is_safe(ha):
    """A final person event with null identity remains Unknown, never Known/fabricated."""
    ev = {"type": "end", "before": {}, "after": {
        "id": "end-unknown", "camera": "front_door", "label": "person",
        "sub_label": None, "score": 0.81,
    }}
    result = ha.render(ev, json.loads(json.dumps(cases.BASE_MAPPING)), MappingStatus.LOADED)
    assert result["outcome"] == "IDENTITY_UNKNOWN"
    assert result["known"] is False
    assert result["identity"] is None
    assert result["recognition_confidence"] is None
    assert result["detection_confidence"] == 0.81


def test_absent_vs_broken_distinguished(ha):
    base = json.loads(json.dumps(cases.BASE_MAPPING))
    absent = {"type": "update", "before": {}, "after": {
        "id": "abs", "camera": "front_door", "label": "person",
        "sub_label": "Totally_Absent", "sub_label_score": 0.9}}
    broken = {"type": "update", "before": {}, "after": {
        "id": "brk", "camera": "front_door", "label": "person",
        "sub_label": "Entry_Not_Object", "sub_label_score": 0.9}}
    for ev, expected in ((absent, "IDENTITY_UNMAPPED"), (broken, "MAPPING_UNAVAILABLE")):
        py = _oracle(ev, base, MappingStatus.LOADED)
        hj = ha.render(ev, base, MappingStatus.LOADED)
        assert py["outcome"] == expected
        assert not diff_fields(py, hj)
