# Live Home Assistant Integration — Preflight / Planning

**Feature**: [Front Door Person Identification](../../specs/001-front-door-person-identification/spec.md)
**Status**: PLANNING / READ-ONLY PREFLIGHT ONLY — no live Home Assistant change is authorized
by this document.
**Companion**: [production-deployment.md](production-deployment.md) ·
[mqtt-events contract](../../specs/001-front-door-person-identification/contracts/mqtt-events.md) ·
[C2 isolated fixture](../../home-assistant/tests/c2_2/README.md)

> This document plans the eventual live integration of the C2-validated identity
> normalization. **It does not modify live Home Assistant, install any mapping, reload/restart
> HA, or touch Frigate/Ring.** Live implementation is NOT authorized.

---

## Evidence classification (honesty gate)

This preflight was produced from a development Mac. The **production Raspberry Pi 3, its Home
Assistant, and the production/shared MQTT broker were NOT reachable from this environment**
(local Docker stack down; `127.0.0.1:8123` and `homeassistant.local:8123` closed). Every fact
below is tagged with how it was established.

### DIRECTLY VERIFIED (this environment)
- **Dev/throwaway HA** at `home-assistant/throwaway-config/`: HA **2024.12.5**; split-include
  layout (`configuration.yaml` → `automation: !include automations.yaml`, `script:`, `scene:`);
  MQTT configured as a **config entry** (`.storage/core.config_entries` shows `mqtt`/`mosquitto`),
  not YAML broker keys; `automations.yaml` is empty (`[]`); ring-mqtt entities present
  (`binary_sensor.front_door_ding`, `binary_sensor.front_door_motion`, `camera.front_door_snapshot`,
  `switch.front_door_motion_detection`, …); person is `person.phase1_test_admin` (test only).
- **Isolated HA/Jinja normalization** (C2.2) and its **real-HA full config validation** (C2.4):
  `hass --script check_config` PASS on the isolated fixture; `!include` loads; types preserved.
- **Reference↔HA parity** (C2.3): EXACT across all normalized fields (42 tests).
- Prior C2.1–C2.4 artifacts (pushed).

### PRIOR EVIDENCE ONLY (documented, not freshly re-inspected)
- **Production config layout** (Pi HA OS) — per `production-deployment.md`.
- **Existing production Ring automations**: `automation.front_door_doorbell_notification` on
  `event.front_door_ding`; a Front Door Motion Notification automation on
  `event.front_door_motion` — documented, not read from the Pi.
- **Production entities to preserve**: `event.front_door_ding`, `event.front_door_motion`,
  `switch.front_door_motion_detection`, `notify.mobile_app_pk_world`,
  `person.praveen_kumar_konathala` (production-deployment.md Article VIII.1). None of these
  exist in the dev instance.
- **Frigate MQTT contract** (`frigate/events`, `frigate/available`; `after.sub_label` scalar
  string|null, `after.sub_label_score` recognition, `after.score` detection) — verified in
  **T034-A against Frigate 0.17.2**, not re-probed live now.
- **Production HA/MQTT integration facts** — documented.

### BLOCKED / NOT YET VERIFIED (requires Pi access — Gate A)
- Exact production mapping **destination path**.
- Exact mapping **transfer/deployment method** and **permissions/ownership**.
- **Fresh production config snapshot**.
- **Fresh production Ring automation capture** (exact trigger/condition/action bodies).
- **Fresh broker/topic verification** on the production/shared broker.
- **Exact reload action** required on the production HA after `!include` mapping regeneration.

---

## Gate A — Production read-only capture (NEXT future phase; NOT executed here)

Gate A is **strictly read-only** on the Pi. Collect before any implementation:

- **A.** Home Assistant version
- **B.** config root + layout
- **C.** `configuration.yaml` include structure
- **D.** automation storage mode (`automations.yaml` / split YAML / UI-managed `.storage` / mix)
- **E.** existing Ring **doorbell** automation definition (verbatim)
- **F.** existing Ring **motion** automation definition (verbatim, incl. any cooldown)
- **G.** MQTT integration/broker status
- **H.** Frigate MQTT topic visibility (if broker reachable) — read-only subscribe only
- **I.** exact candidate location for `relationship_mapping.generated.yaml`
- **J.** permissions/ownership of that destination
- **K.** safe deployment mechanism available (Samba / SSH-SCP / HA file editor / other approved)
- **L.** exact reload required for updated `!include` content (reload domain vs restart)

Gate A does not modify anything; it only captures state and backups.

---

## Ring independence (NON-NEGOTIABLE)

```
event.front_door_ding    → existing Ring doorbell automation   (independent)
event.front_door_motion  → existing Ring motion automation      (independent)

frigate/events → HA normalization → HA event → enriched notification  (additive, separate)
```

The AI path is **additive**. It never sits in the trigger/condition/action path of the Ring
automations. AI failure (Frigate down, MQTT down, malformed event, missing/broken mapping,
template error) must never suppress the Ring path.

**RING_SECURITY_PATH_DEPENDENT_ON_AI = NO.** No future plan may replace the existing Ring
automations with AI-dependent logic.

---

## Event lifecycle policy (provisional)

- Correlate by `after.id` (Frigate `event_id`).
- Conservative default: **normalize + notify once per `event_id`, at the `end` lifecycle**
  (stable identity, `end_time` set). `update` may be observed only to upgrade Unknown→Known
  before end; intermediate updates never fire their own notification.
- `frigate/available` offline / stale (no `end`) → `Unavailable`, never silent `Unknown`.

`LIFECYCLE_POLICY_DEFINED = YES`; `LIVE_LIFECYCLE_BEHAVIOR_FRESHLY_VERIFIED = NO` — the real
`new`/`update`/`end` behavior must be confirmed against live production event traces before
enabling.

---

## Dedup / correlation (design)

- **Primary key**: `after.id` (event_id). At most one enriched notification per event.
- **Secondary suppression (PROPOSED, not implemented)**: a 5-minute per-person window
  (FR-030). This is a proposal in this plan; it is **not** yet ratified/implemented.
- This dedup applies **only to the new AI enriched notification**. It must **not** suppress
  the existing Ring ding or motion notifications (which are independent automations).
- Prefer native trigger-scoped variables / automation `mode: single` over persistent helpers
  to minimize PII persistence; create no helpers during planning.

---

## Normalized output contract (design)

- **Mechanism**: fire an HA **custom event** (e.g. `front_door_identity_normalized`) carrying
  the normalized fields; a separate notification automation consumes it.
- **Why**: useful for downstream automations; avoids unnecessary persistent PII; avoids a
  custom bridge/service; keeps HA as the control plane.
- MQTT re-publish and persistent helper entities are **NOT mandatory** and are not planned
  unless later approved.
- Fields: `outcome, known, raw_identity, identity, person_uuid, relationship, enabled,
  recognition_confidence, detection_confidence, reason, frigate_event_id, camera, lifecycle,
  timestamp`.

---

## Mapping deployment (BLOCKED — pending Gate A)

- Source of truth: enrollment DB. Derived artifact: `relationship_mapping.generated.yaml`
  (gitignored, never committed; currently **not present / not installed** — only the
  `.example` exists).
- Live destination path, transfer method, permissions/ownership: **undecided** — production-
  deployment.md leaves this **pending Phase 4**. `MAPPING_DEPLOYMENT_PATH_DEFINED = PARTIAL`.
- Atomic replacement: temp file + `os.replace` on the target (matches the C1 exporter's own
  atomic write). No automatic deployment daemon.
- **Reload**: `!include` resolves at **config/automation load**, not per-execution → after
  regenerating the mapping, HA must reload the consuming domain (or restart) for new data to
  apply. `HA_INCLUDE_RELOAD_BEHAVIOR_DEFINED = YES`;
  `HA_INCLUDE_RELOAD_BEHAVIOR_TARGET_CONFIRMED = NO` (must confirm the exact reload action on
  the Pi at Gate A).

### Mapping failure policy (fail-closed; unchanged from C2 contract)
- valid mapping + absent identity → `IDENTITY_UNMAPPED` (known=false)
- broken/missing/unsupported mapping → `MAPPING_UNAVAILABLE` (known=false)
- disabled entry → `IDENTITY_DISABLED` (known=false, trusted fields null)
- No stale previously-known identity may leak through.

---

## Normalization location

- **MQTT-triggered automation** (trigger: `mqtt` on `frigate/events`) running the validated
  C2.2 Jinja normalization inline or via a called `script`. Simplest HA-native form matching
  the ratified "no custom bridge" architecture and the C2-validated fixture.
- **NO** custom integration, pyscript, AppDaemon, or Python daemon.

---

## Notifications (design; separate from Ring)

Calls `notify.mobile_app_pk_world` from a **new** automation:
- KNOWN → "Front Door: {display_name} detected — {relationship}" (no UUID)
- UNKNOWN → "Front Door: Unknown person detected"
- DISABLED → suppress or generic "person detected" (never reveal a disabled identity's name)
- UNMAPPED → generic "person detected" (never a name; no relationship configured)
- MAPPING_UNAVAILABLE / RECOGNITION_FAILURE → diagnostic/log-only; must not masquerade as an
  Unknown *identity* claim nor as Known
- IGNORED_NON_PERSON → no notification

Conservative safety: low confidence / unmapped / disabled / recognition failure / missing
mapping are **never** Known. False Unknown is preferable to false identity. No relationship is
ever inferred from appearance.

---

## Privacy / retention

- **No biometric media, face crops, or embeddings in HA** — those stay in Frigate's data
  volume.
- Prefer **transient HA events** over recorded state. Keep `person_uuid` and `raw_identity`
  **out of long-term HA recorder state** unless explicitly needed for diagnostics; exclude any
  identity/UUID attributes from the recorder if a sensor is later introduced.
- An `Unknown` result never becomes a stored identity (constitution II.1/II.2).

---

## Backup (run at Gate A — not now)
- Back up `configuration.yaml`, the relevant automations file/include, helper/include files.
- Capture existing Ring automation definitions and preserved-entity states (read-only).
- Record HA version + MQTT integration status.
- Prefer a **full HA OS backup/snapshot** on the Pi.

## Rollback
1. Disable/delete only the new AI normalization + notification automations.
2. Remove the generated relationship-mapping `!include` if added.
3. Restore backed-up config file(s) if any were touched.
4. Reload/restart HA safely.
5. Verify `automation.front_door_doorbell_notification` fires on `event.front_door_ding`.
6. Verify the motion automation fires on `event.front_door_motion`.

Existing Ring functionality must not depend on rolling back Frigate itself.

---

## Proposed future file plan (verify actual Pi layout at Gate A)
| Path (candidate) | Action | Purpose | Live/Generated | Rollback |
|---|---|---|---|---|
| `<HA config>/automations.yaml` (or `automations/front_door_identity.yaml`) | modify/create | MQTT-triggered normalization + separate notification automation | live | delete added block/file |
| `<HA config>/helpers/relationship_mapping.generated.yaml` | create | real mapping via `!include` | generated (gitignored) | remove file + include |
| `<HA config>/configuration.yaml` | modify only if needed | add include/template block | live | restore backup |

---

## Implementation gates (defined; NOT executed)
- **A** Production read-only capture + backups
- **B** Deploy generated real mapping only
- **C** HA config check with mapping present
- **D** Install new AI automation disabled / no notifications
- **E** Config validation
- **F** Enable normalization (fire HA event only)
- **G** Synthetic MQTT test (bounded, isolated) if safe
- **H** Real front-door walk test (bounded Ring stream)
- **I** Enable enriched notifications
- **J** Failure-isolation test: disable Frigate AI path → Ring ding/motion still notify (T053)

---

## Readiness gaps
- **BLOCKER**: Pi write access + read-only capture of existing Ring automation bodies; mapping
  deployment destination + transfer method; fresh production MQTT/Frigate reachability.
- **REQUIRED BEFORE ENABLE**: exact HA reload mechanism after mapping regen (on target);
  finalize lifecycle (`update` vs `end`) + dedup against real traces; confirm HA-event output
  + recorder exclusions; capture backups.
- **OPTIONAL LATER**: dashboard sensor, richer observability, multi-camera expansion.

---

## No-change verification (this preflight)
- production HA contacted for writes: NO (Pi unreachable)
- configuration modified: NO
- mapping deployed: NO
- HA reload/restart: NO
- new automation: NO
- new helper: NO
- live MQTT publish: NO
- Frigate modified: NO
- Ring modified: NO
