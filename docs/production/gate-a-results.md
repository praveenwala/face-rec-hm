# Gate A — Production Read-Only Capture: Results

**Feature**: [Front Door Person Identification](../../specs/001-front-door-person-identification/spec.md)
**Status**: COMPLETE (read-only) — Gate A was executed by the operator and reviewed. These are
the **sanitized** results. No production change was made; live implementation is NOT authorized.
**Companion**: [gate-a-execution-authorization.md](gate-a-execution-authorization.md) ·
[gate-a-preparation.md](gate-a-preparation.md) ·
[live-ha-integration-preflight.md](live-ha-integration-preflight.md) ·
[production-deployment.md](production-deployment.md)

> Evidence here is **FRESHLY_VERIFIED** on the production Raspberry Pi during Gate A (operator-
> executed, read-only) unless explicitly marked otherwise. Sanitized: no secrets, tokens,
> credentials, household UUIDs, biometric media, or `.storage` dumps.

---

## Home Assistant (FRESHLY_VERIFIED)

| Fact | Value |
|---|---|
| HA Core | 2026.9.1 |
| HA OS | 18.2 |
| Supervisor | 2026.09.0 |
| architecture | aarch64 |
| machine | raspberrypi3-64 |
| state | running / supported |
| timezone | America/Chicago |

## Configuration layout (FRESHLY_VERIFIED)

- canonical config root: `/homeassistant`
- `/config` is a symlink to `/homeassistant`
- `configuration.yaml` exists
- `automations.yaml` exists
- `scripts.yaml` exists (currently empty)
- `scenes.yaml` exists (currently empty)
- `configuration.yaml` includes:
  - `automation: !include automations.yaml`
  - `script: !include scripts.yaml`
  - `scene: !include scenes.yaml`
- themes use `!include_dir_merge_named`
- **no existing `helpers` directory observed**
- **no existing relationship-mapping include observed**

## Ring security path — independence (FRESHLY_VERIFIED)

- `event.front_door_ding` → existing **Front Door Doorbell Notification** automation
- `event.front_door_motion` → existing **Front Door Motion Notification** automation
- both notify via `notify.mobile_app_pk_world`
- motion automation retains its existing **>300 second `last_triggered` cooldown**
- neither path references Frigate, face recognition, the generated relationship mapping, or
  the proposed AI path
- **`RING_SECURITY_PATH_DEPENDENT_ON_AI = NO`**

**Architectural invariant (preserved):** Ring security notifications remain independent of the
AI/Frigate pipeline and must continue working if the AI pipeline is unavailable. The AI path is
additive only.

## MQTT / Frigate event transport (BLOCKED / UNVERIFIED)

> **SUPERSEDED for CURRENT state** (2026-09-14): Mosquitto was subsequently installed and the HA
> MQTT integration configured during PRE-B3-A. This section remains accurate **as of Gate A**;
> for current MQTT state see [mqtt-state-reconciliation.md](mqtt-state-reconciliation.md).

- Home Assistant **MQTT integration is not currently configured** on production
- the official Mosquitto broker app is **available but not installed**
- therefore `frigate/available` and `frigate/events` were **NOT freshly observed** from
  production during Gate A
- classification: **BLOCKED / UNVERIFIED** — this is a required-before-enable gap, **not** a
  failure. Production MQTT is **not** claimed to be working.

## Deployment tooling (FRESHLY_VERIFIED availability)

- Samba Share: available, **not installed**
- File Editor: available, **not installed**
- existing Terminal/SSH environment has access to `/homeassistant`
- **no additional add-on should be installed solely for mapping deployment**
- exact final mapping destination remains intentionally **PARTIAL / unselected**
  (`MAPPING_DEPLOYMENT_PATH_DEFINED = PARTIAL`). A `helpers` directory does not yet exist; if
  chosen later it would be created deliberately during live implementation (not now).

## Reload semantics (UNKNOWN)

- `ha core check` is available on the target
- no useful production automation-reload evidence was found
- **do not claim `automation.reload` is sufficient**
- `TARGET_MAPPING_RELOAD_SEMANTICS = UNKNOWN` — the exact reload/restart required after mapping
  replacement must be resolved before live deployment.
- `HA_INCLUDE_RELOAD_BEHAVIOR_TARGET_CONFIRMED = NO`

## Backup planning (for live implementation; none created now)

- **mandatory targeted backups:** `configuration.yaml`, `automations.yaml`
- prefer a normal full **Home Assistant backup** before live implementation
- do **not** copy/dump `.storage` into tracked documentation
- do **not** expose `secrets.yaml`

## Gate A safety (no-change proof — FRESHLY_VERIFIED)

- no production files modified
- no automation modified
- no add-on installed
- no MQTT publication
- no HA reload
- no HA restart
- no generated mapping installed
- `LIVE_HA_UNCHANGED = YES`

## Explicit unresolved blockers (before live implementation)

1. **Production MQTT/Frigate event transport is not yet configured/verified** (MQTT
   integration + broker not installed). — BLOCKER
2. **Exact production mapping destination not yet selected** (no `helpers` dir; path PARTIAL). —
   REQUIRED BEFORE ENABLE
3. **Target-specific mapping include reload behavior UNKNOWN** (must be resolved). — REQUIRED
   BEFORE ENABLE

## Status flags (Gate A)

- `GATE_A_PRODUCTION_READ_ONLY_CAPTURE = PASS`
- `PRODUCTION_PI_REACHABLE = YES` (operator-executed)
- `LIVE_CONFIG_LAYOUT_FRESHLY_VERIFIED = YES`
- `EXISTING_RING_AUTOMATIONS_FRESHLY_VERIFIED = YES`
- `RING_SECURITY_PATH_DEPENDENT_ON_AI = NO`
- `MQTT_INTEGRATION_FRESHLY_VERIFIED = NO` (not configured on production)
- `FRIGATE_MQTT_FRESHLY_VERIFIED = BLOCKED` (no broker; not observed)
- `MAPPING_DEPLOYMENT_PATH_DEFINED = PARTIAL`
- `MAPPING_TRANSFER_METHOD_DEFINED = PARTIAL` (Terminal/SSH has `/homeassistant` access; final
  method not finalized; no add-on to be installed solely for deployment)
- `HA_INCLUDE_RELOAD_BEHAVIOR_TARGET_CONFIRMED = NO`
- `PRODUCTION_BACKUP_TARGETS_DEFINED = YES`
- `MUTATING_ACTIONS_PERFORMED = NO`
- `LIVE_HA_UNCHANGED = YES`
- `SAFE_TO_BEGIN_LIVE_IMPLEMENTATION = NO`
- `SAFE_TO_MODIFY_LIVE_HOME_ASSISTANT = NO`
