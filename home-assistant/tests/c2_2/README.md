# T034-C2.2 — Isolated HA Jinja Identity Normalization Fixture

**THIS IS NOT LIVE HOME ASSISTANT CONFIG.** Nothing here is loaded by the dev throwaway HA
instance (`home-assistant/throwaway-config/`) or by the production Raspberry Pi. It is a
self-contained, offline test fixture that exists only to implement and validate the
Home-Assistant-native Jinja identity-normalization logic against the C2.1 reference oracle.

- No live HA modification.
- No MQTT subscription/publish, no notifications, no automations that act.
- No Frigate, no Ring, no enrollment, no threshold changes.
- No custom integration, no pyscript, no AppDaemon, no runtime Python service.
- Synthetic identities only — no real household identity/UUID/relationship, no secrets, no media.

## Purpose

C2.1 produced the authoritative reference oracle `bridge/identity_normalizer.py` (a pure,
test-only Python model of the identity-normalization contract). C2.2 implements the same
contract in **HA-native Jinja** and proves parity using the **real Home Assistant template
engine** — not a hand-rolled Jinja renderer.

The Jinja macro (`templates/identity_normalization.jinja`) mirrors the reference model
exactly:

- deterministic outcome precedence (1..9): IGNORED_NON_PERSON → RECOGNITION_FAILURE
  (malformed) → IDENTITY_UNKNOWN → RECOGNITION_FAILURE (missing/invalid recognition score)
  → MAPPING_UNAVAILABLE (global) → IDENTITY_UNMAPPED → MAPPING_UNAVAILABLE (broken entry)
  → IDENTITY_DISABLED → IDENTITY_KNOWN;
- trust rule: `known=true` only for a fully-valid enabled entry;
- fail-closed on missing/invalid recognition score, **never** substituting `after.score`;
- absent (`IDENTITY_UNMAPPED`) vs broken (`MAPPING_UNAVAILABLE`) kept distinct;
- `enabled==false` → `IDENTITY_DISABLED` with trusted metadata (identity/uuid/relationship) null.

## Files

| File | Role |
|---|---|
| `configuration.yaml` | Isolated HA config; validates the `!include` shape for the mapping. |
| `automations.yaml` | Intentionally empty (`[]`). |
| `helpers/relationship_mapping.synthetic.yaml` | Synthetic mapping in the exact C1 exporter schema (`schema_version: 1` + `identities`). |
| `fixtures/synthetic_events.json` | 20 synthetic `frigate/events`-style inputs (cases A–T) + expected results. |
| `templates/identity_normalization.jinja` | The HA-native normalization macro (mirrors C2.1). |
| `run_c2_2_cases.py` | Harness: renders the macro through the **real HA `Template` engine** and cross-checks each field against both the declared expectation and the live C2.1 oracle. |
| `.gitignore` | Excludes the throwaway `.ha-venv/` and caches (not tracked). |

## Synthetic mapping schema (matches C1 exactly)

```yaml
schema_version: 1
identities:
  "<frigate_identity_name>":
    person_uuid: "..."
    display_name: "..."
    relationship: "Family|Friend|Neighbor|Other Known"
    enabled: true|false
```

Included synthetic entries: `Known_Person_A` (enabled Family), `Known_Person_B` (disabled),
`José` (Unicode), `"true"` (YAML-looking string key), plus deliberately broken entries
(`Bad_Relationship`, `Wrong_Enabled_Type`, `Missing_UUID`, `Missing_Display_Name`,
`Disabled_Malformed`, `Not_An_Object`) to exercise the fail-closed / broken-entry paths.

## How the synthetic mapping is loaded (HA `!include`)

`configuration.yaml` loads the mapping into a template's variable scope via the native
include mechanism, then exposes a probe sensor so `check_config` validates the include and
the resulting object shape:

```yaml
template:
  - sensor:
      - name: "C2_2 Relationship Mapping Probe"
        state: "{{ 'LOADED' if (mapping is mapping and mapping.schema_version == 1) else 'INVALID' }}"
        variables:
          mapping: !include helpers/relationship_mapping.synthetic.yaml
```

`hass --script check_config` reports this file under **"yaml files (used)"**, confirming the
include resolves. `HA_INCLUDE_SHAPE_VALIDATED = YES`.

## How synthetic inputs are exercised

`run_c2_2_cases.py` reads each case from `fixtures/synthetic_events.json`, renders
`normalize(ev, mapping, mapping_status)` through `homeassistant.helpers.template.Template`
(the real HA engine, HA 2024.12.5), parses the JSON result, and compares all nine
normalized fields to (1) the case's `expect` block and (2) the C2.1 oracle
(`bridge.identity_normalizer.normalize_identity` fed by the T034-A parser) on the same input.

## Commands (one-time setup + run)

The isolated environment installs real Home Assistant into a throwaway venv (nothing
touches any live service). The venv is gitignored.

```bash
cd home-assistant/tests/c2_2

# one-time: create throwaway venv + install the exact HA version (2024.12.5)
python3 -m venv .ha-venv
source .ha-venv/bin/activate
pip install --upgrade pip wheel
pip install "homeassistant==2024.12.5"

# 1) validate the !include shape + template config through REAL HA
hass --script check_config -c .            # expect exit 0, config VALID, mapping file "used"

# 2) run all synthetic cases through the REAL HA Template engine and cross-check the oracle
python run_c2_2_cases.py                    # expect: 20/20 PASS; semantic drift: 0
```

## Expected outcomes (cases A–T)

| Case | Input summary | Expected outcome |
|---|---|---|
| A | enabled Family, recog+det present | IDENTITY_KNOWN (known=true) |
| B | null sub_label | IDENTITY_UNKNOWN |
| C | disabled entry | IDENTITY_DISABLED (trusted null) |
| D | identity absent from mapping | IDENTITY_UNMAPPED |
| E | enabled entry, invalid relationship | MAPPING_UNAVAILABLE |
| F | mapping_status=MISSING | MAPPING_UNAVAILABLE |
| G | schema_version=2 | MAPPING_UNAVAILABLE |
| H | malformed sub_label (list) | RECOGNITION_FAILURE |
| I | whitespace sub_label | IDENTITY_UNKNOWN |
| J | recog 0.93 / det 0.84 | IDENTITY_KNOWN, fields distinct |
| K | missing sub_label_score | RECOGNITION_FAILURE (det preserved, not substituted) |
| L | sub_label_score = true (bool) | RECOGNITION_FAILURE |
| M | label=car | IGNORED_NON_PERSON |
| N | enabled is a string | MAPPING_UNAVAILABLE |
| O | enabled entry missing uuid | MAPPING_UNAVAILABLE |
| P | enabled entry missing display_name | MAPPING_UNAVAILABLE |
| Q | sub_label = "true" | IDENTITY_KNOWN (exact string lookup) |
| R | sub_label = "José" | IDENTITY_KNOWN (Unicode preserved) |
| S | null render after a known render | IDENTITY_UNKNOWN (no stale leakage) |
| T | disabled + malformed metadata | IDENTITY_DISABLED |

## Cleanup

```bash
cd home-assistant/tests/c2_2
deactivate 2>/dev/null || true
rm -rf .ha-venv __pycache__            # removes the throwaway HA runtime + caches
```

The tracked fixture files (config, mapping, events, jinja, harness, README, .gitignore) are
static text and safe to leave in the repo. Removing the whole `home-assistant/tests/c2_2/`
directory fully reverts the fixture; it has no effect on any live/dev/production HA config.

## Not-live statement

This fixture performs **no** live integration. It does not connect to MQTT, does not talk to
Frigate or Ring, does not run automations, does not enroll anyone, and does not modify any
live/dev/production Home Assistant configuration. Runtime wiring is deferred to a later phase
(C2.3+) and is explicitly out of scope for C2.2.
