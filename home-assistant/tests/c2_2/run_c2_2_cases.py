#!/usr/bin/env python3
"""T034-C2.2 isolated HA/Jinja normalization harness (TEST FIXTURE ONLY).

Renders the HA-native normalization macro (templates/identity_normalization.jinja) through
the REAL Home Assistant Template engine (homeassistant.helpers.template.Template) for every
synthetic case in fixtures/synthetic_events.json, then compares each rendered result field
to BOTH:
  1. the case's declared `expect` block, and
  2. the C2.1 reference oracle (bridge/identity_normalizer.py) run on the same inputs.

This proves HA/Jinja parity with the reference model using real HA semantics (not a
hand-rolled Jinja renderer). No live HA, no MQTT, no Frigate, no network, no mutation.

Usage:
  source .ha-venv/bin/activate
  python run_c2_2_cases.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]  # home-assistant/tests/c2_2 -> repo root
MACRO = HERE / "templates" / "identity_normalization.jinja"
MAPPING_YAML = HERE / "helpers" / "relationship_mapping.synthetic.yaml"
EVENTS = HERE / "fixtures" / "synthetic_events.json"

# --- real HA template engine ---
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.helpers.template import Template  # noqa: E402
import yaml  # noqa: E402

# --- C2.1 reference oracle (authoritative contract) ---
sys.path.insert(0, str(REPO_ROOT))
from bridge.frigate_event_parser import parse_event  # noqa: E402
from bridge.identity_normalizer import normalize_identity, MappingStatus  # noqa: E402

FIELDS = [
    "outcome", "known", "raw_identity", "identity", "person_uuid",
    "relationship", "enabled", "recognition_confidence", "detection_confidence",
]


def _load_mapping() -> dict:
    return yaml.safe_load(MAPPING_YAML.read_text(encoding="utf-8"))


def _macro_body() -> str:
    return MACRO.read_text(encoding="utf-8")


def _render(hass: HomeAssistant, ev: dict, mapping, mapping_status: str) -> dict:
    """Render the macro through the real HA Template engine and parse the JSON result."""
    body = _macro_body()
    tpl_str = (
        body
        + "\n{{- normalize(ev, mapping, mapping_status) -}}"
    )
    tpl = Template(tpl_str, hass)
    out = tpl.async_render(
        {"ev": ev, "mapping": mapping, "mapping_status": mapping_status},
        parse_result=False,
    )
    return json.loads(out)


def _oracle(ev: dict, mapping, mapping_status: str) -> dict:
    parsed = parse_event(ev)
    r = normalize_identity(parsed, mapping, mapping_status)
    return {
        "outcome": r.outcome,
        "known": r.known,
        "raw_identity": r.raw_identity,
        "identity": r.identity,
        "person_uuid": r.person_uuid,
        "relationship": r.relationship,
        "enabled": r.enabled,
        "recognition_confidence": r.recognition_confidence,
        "detection_confidence": r.detection_confidence,
    }


def _norm_num(v):
    # normalize float comparison (json floats vs python floats)
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return ("__invalid__",)
    return v


def _cmp(a: dict, b: dict) -> list[str]:
    diffs = []
    for f in FIELDS:
        av, bv = _norm_num(a.get(f)), _norm_num(b.get(f))
        if isinstance(av, (int, float)) and isinstance(bv, (int, float)) and not isinstance(av, bool) and not isinstance(bv, bool):
            if abs(float(av) - float(bv)) > 1e-9:
                diffs.append(f"{f}: {av!r} != {bv!r}")
        elif av != bv:
            diffs.append(f"{f}: {av!r} != {bv!r}")
    return diffs


def main() -> int:
    import asyncio

    mapping_base = _load_mapping()
    cases = json.loads(EVENTS.read_text(encoding="utf-8"))["cases"]

    async def _run() -> int:
        hass = HomeAssistant(str(HERE))  # config dir; no services started (loop is running)

        total = 0
        passed = 0
        drift = 0
        print(f"HA/Jinja isolated normalization harness — {len(cases)} cases\n")
        for c in cases:
            total += 1
            cid = c["id"]
            ev = c["event"]
            status = c.get("mapping_status", "LOADED")
            mapping = None if status != "LOADED" else json.loads(json.dumps(mapping_base))
            if "mapping_schema_override" in c and mapping is not None:
                mapping["schema_version"] = c["mapping_schema_override"]

            rendered = _render(hass, ev, mapping, status)
            oracle = _oracle(ev, mapping, status)
            expect = c["expect"]

            d_expect = _cmp(rendered, expect)
            d_oracle = _cmp(rendered, oracle)
            ok = not d_expect and not d_oracle
            if ok:
                passed += 1
            if d_oracle:
                drift += 1
            status_str = "PASS" if ok else "FAIL"
            print(f"[{status_str}] {cid}: HA outcome={rendered['outcome']} known={rendered['known']}")
            if d_expect:
                print(f"     vs EXPECT: {d_expect}")
            if d_oracle:
                print(f"     vs ORACLE(C2.1): {d_oracle}")

        print(f"\n=== {passed}/{total} cases PASS; semantic drift vs C2.1 oracle: {drift} ===")
        await hass.async_stop(force=True)
        return 0 if passed == total and drift == 0 else 1

    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
