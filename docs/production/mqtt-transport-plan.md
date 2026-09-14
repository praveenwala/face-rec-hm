# MQTT / Frigate Transport — Blocker 1 Resolution Plan

**Feature**: [Front Door Person Identification](../../specs/001-front-door-person-identification/spec.md)
**Status**: PLANNING ONLY — no production contact, no Mosquitto install, no MQTT config, no
Frigate/Ring change. Blockers 2 (mapping path) and 3 (reload semantics) are out of scope here.
**Companion**: [gate-a-results.md](gate-a-results.md) · [production-deployment.md](production-deployment.md) ·
[mqtt-events contract](../../specs/001-front-door-person-identification/contracts/mqtt-events.md)

---

## 1. Architecture reconciliation (tracked evidence)

From `production-deployment.md` (authoritative) + dev `docker-compose.yml`/`frigate/config/config.yml`:

| Component | Intended production location | Evidence |
|---|---|---|
| Home Assistant (control plane) | Raspberry Pi 3 (aarch64, HA OS 18.2, Core 2026.9.1) | Gate A FRESHLY_VERIFIED |
| Frigate + person/face recognition | separate, not-yet-selected AI compute host (NOT the Pi) | production-deployment.md §B |
| MQTT broker | **shared, authenticated broker both hosts use** | production-deployment.md §A "same MQTT broker" |
| Ring/video bridge (ring-mqtt + go2rtc) | AI host (or a small always-on device) | production-deployment.md §Ring bridge |
| Enrollment manager + generated mapping | derived artifact; DB is source of truth | production-deployment.md §Relationship mapping |

**Prior-doc broker assumption:** production-deployment.md leans toward **(A) broker on the HA
Pi** ("Mosquitto ... a standard Home Assistant add-on ... Pi-appropriate ... not an AI
workload") while requiring only that both hosts share **one authenticated broker**. The dev POC
uses a single-host Mosquitto container (`mosquitto:1883`, anonymous) — POC-only, not production.

**Invariants preserved (unchanged):** Pi 3 is HA-only; Frigate/AI on separate compute; Ring
native security automations independent; AI failure must not break Ring notifications; MQTT is
event-bus only (no video); no custom Python runtime bridge; HA Jinja is the normalization
runtime; face recognition never grants physical access.

## 2–3. Broker placement — options and decision

| | A: Mosquitto add-on on HA Pi | B: Mosquitto on Frigate/AI host | C: existing external LAN broker |
|---|---|---|---|
| Reliability | Pi is always-on control plane | tied to AI host uptime | depends on that device |
| Pi 3 resource impact | small (broker is light; not AI) | none | none |
| Local-first | yes | yes | yes |
| HA integration simplicity | highest (localhost broker) | medium | medium |
| Frigate integration | medium (points at Pi) | highest (localhost) | medium |
| Failure isolation | broker up whenever Pi/HA is up | broker dies with AI host | independent |
| Credential mgmt | HA add-on manages users | manual | manual |
| Backup/recovery | part of HA backup | separate | separate |
| Op complexity | lowest (one managed add-on) | higher | higher (extra device) |

**Decision: OPTION A — Mosquitto broker as the official Home Assistant add-on on the Pi 3.**

Rationale (project-specific):
- The Pi is already the always-on control plane; a light broker there is explicitly sanctioned
  by `production-deployment.md` and is **not** an AI workload (respects constitution I.1/I.2).
- The HA MQTT integration then connects to a **local** broker — simplest, most reliable HA-side
  path; the AI host connects over LAN.
- **Failure behavior:** if the **AI/Frigate host is down**, the broker (on the Pi) stays up, HA
  stays responsive, and — critically — the **Ring ding/motion automations are unaffected**
  because they are driven by the Ring integration, not MQTT/Frigate. If the **broker is down**
  (i.e., the Pi/HA itself is down), the whole control plane is down regardless — but Frigate can
  continue local video/person detection and simply cannot deliver events until the broker
  returns (events are transient; no Ring dependency). Ring security notifications never depend
  on the broker or Frigate.
- Pi 3 resource limits are acceptable for a single-camera event bus (metadata only, no video).

`BROKER_PLACEMENT_DECISION = YES`; `SELECTED_BROKER_LOCATION = HOME_ASSISTANT_PI`.

## 4. Network flow (VIDEO vs EVENT/METADATA separated)

```
VIDEO PATH (never over MQTT):
  Ring → ring-mqtt (cloud auth) → go2rtc/RTSP → Frigate (decode + detect + face recognition)

EVENT / METADATA PATH (MQTT, metadata only):
  Frigate → MQTT broker (Mosquitto on Pi) → HA MQTT integration
          → HA MQTT-triggered automation (C2 Jinja normalization)
          → future enriched notification (notify.mobile_app_pk_world)
```

MQTT carries **event metadata only** — never video, images, crops, or embeddings.

## 5. Required MQTT topics (smallest set)

| Topic | Producer | Consumer | Payload purpose | Retained | Required |
|---|---|---|---|---|---|
| `frigate/events` | Frigate | HA | person-detection lifecycle (`new`/`update`/`end`) + recognition (`after.id`, `camera`, `label`, `sub_label`, `sub_label_score`; detection `after.score` kept separate) | non-retained (event stream) | REQUIRED |
| `frigate/available` | Frigate | HA | Frigate online/offline → HA "AI host offline" → `Unavailable` (never silent Unknown) | typically retained (LWT/birth) | REQUIRED |

No other Frigate topics are required for Feature 001. No invented fields — matches the T034-A /
mqtt-events contract exactly. (`topic_prefix: frigate` on the Frigate side.)

## 6. Authentication (least privilege; NO real credentials here)

Conceptual accounts/roles (placeholders only):
- **frigate_pub** — Frigate client: **publish only** to `frigate/#` (or specifically
  `frigate/events`, `frigate/available`). No subscribe needed.
- **ha_sub** — Home Assistant client: **subscribe only** to `frigate/events` and
  `frigate/available`. **Publish NOT required** for Feature 001 (normalization output is an
  internal HA event, not an MQTT re-publish) → do not grant publish.
- **Anonymous access: DISABLED** (production must authenticate — unlike the dev POC's
  `allow_anonymous`).

ACL intent: Frigate publishes only its own topics; HA subscribes only to the two required
topics; neither has broader access.

## 7. Network exposure

- listener: LAN interface only (broker bound to the local network, reachable by the AI host)
- port: 1883 (plain MQTT on trusted LAN) — TLS optional for a single trusted LAN segment; if the
  LAN is not fully trusted, use 8883 + TLS. Decision deferred to deployment; **not** required to
  block planning.
- firewall: broker reachable only within LAN
- **`BROKER_PUBLIC_INTERNET_EXPOSURE = NO`** — no router port-forwarding; no external reachability

## 8. Home Assistant MQTT integration plan (conceptual; not performed)

1. Install the official Mosquitto broker add-on on the Pi (deployment phase, not now).
2. Add the MQTT integration pointing at the local broker host/IP (from a gitignored source; no
   secret in repo/report).
3. Authentication: the `ha_sub` account credentials supplied out-of-band.
4. **Discovery decision: ENABLE** MQTT discovery (standard for the Frigate HA integration to
   surface entities); revisit only if it creates unwanted entities.
5. Reconnect: rely on HA's built-in MQTT auto-reconnect.
6. Verify read-only after setup: integration shows "connected"; observe `frigate/available`.
7. **Publish from HA: NOT required** for this feature.

## 9. Frigate MQTT plan (conceptual; not performed; placeholders only)

```yaml
mqtt:
  host: <broker-host>       # placeholder — the Pi's LAN address
  port: <1883|8883>
  user: <frigate_pub>       # placeholder
  password: <secret>        # out-of-band, never committed
  topic_prefix: frigate
  # client_id: <optional>
```

Dev evidence: `frigate/config/config.yml` already has `mqtt: host: mosquitto / port: 1883 /
topic_prefix: frigate` (POC single-host, anonymous). Production Frigate runs on the not-yet-
selected AI host and its config was **not observed**.
`FRIGATE_PRODUCTION_MQTT_CONFIG = PRIOR_EVIDENCE_ONLY`.

## 10. Failure isolation

| Scenario | Expected behavior |
|---|---|
| broker down | no AI events delivered; HA/Ring path unaffected (Ring not MQTT-driven); Frigate keeps detecting locally, buffers/loses transient events |
| HA MQTT integration down | no AI enrichment; Ring automations unaffected |
| Frigate down | `frigate/available` offline → `Unavailable` (never silent Unknown); Ring unaffected |
| AI host down | same as Frigate down; broker (on Pi) stays up; HA responsive; Ring unaffected |
| network partition (Pi↔AI) | AI events stop; Ring path (Ring→HA integration) unaffected |
| malformed `frigate/events` | C2 normalizer → RECOGNITION_FAILURE / no trusted output; no crash |
| unknown identity | IDENTITY_UNKNOWN; no false identity |
| recognition failure | RECOGNITION_FAILURE; fail-closed |

**`RING_SECURITY_PATH_DEPENDENT_ON_MQTT = NO`** and
**`RING_SECURITY_PATH_DEPENDENT_ON_FRIGATE = NO`** — structurally, the Ring ding/motion
automations trigger on `event.front_door_ding` / `event.front_door_motion` (Ring integration),
not on MQTT/Frigate.

## 11. Event delivery / dedup assumptions (unchanged, provisional)

- process normalized result at event **`end`**; deduplicate by Frigate `event_id`; one AI
  notification per `event_id`.
- **`SECONDARY_PERSON_DEDUP = PROPOSED_NOT_IMPLEMENTED`** (the 5-minute per-person suppression
  remains a proposal; not ratified/implemented here).

## 12. Privacy

MQTT payloads carry event metadata only. Minimize raw-identity/UUID persistence; keep identity
attributes out of the recorder; avoid debug-logging identity payloads. **No** face crops, video,
embeddings, or photos over MQTT.

## 13. Observability (future validation; no execution now)

1. broker healthy → 2. Frigate connected → 3. HA MQTT integration connected →
4. `frigate/available` observed → 5. bounded `frigate/events` observation →
6. one person event observed → 7. lifecycle verified → 8. `event_id` verified →
9. camera/label verified → 10. `sub_label`/`sub_label_score` behavior verified →
11. confirm HA performs no MQTT publish → 12. existing Ring automations still fire independently.

## 14. Rollback (future MQTT deployment)

Order (must never suppress Ring): (1) disable/remove the HA MQTT integration if needed; (2)
restore Frigate config (remove/revert its `mqtt:` block on the AI host); (3) stop/remove the
Mosquitto add-on **only if** explicitly part of rollback; (4) leave Ring automations untouched
throughout; (5) no mapping dependency exists during the MQTT rollout, so nothing mapping-related
to roll back. Ring ding/motion continue regardless.

## 15. Implementation phase breakdown (each mutating phase needs explicit authorization)

- **MQTT-B1** architecture decision (this doc) — planning
- **MQTT-B2** broker deployment/config preparation — planning
- **MQTT-B3** broker deployment (install Mosquitto add-on, create least-priv users) — MUTATING
- **MQTT-B4** HA MQTT integration (connect, verify) — MUTATING
- **MQTT-B5** Frigate MQTT configuration (AI host) — MUTATING
- **MQTT-B6** read-only topic validation — read-only
- **MQTT-B7** failure-isolation regression (AI down → Ring still works, T053) — read-only/observational
- **MQTT-B8** documentation/checkpoint

## 16. Security review

Design requires **no** anonymous MQTT, **no** public-Internet broker, **no** committed
credentials/secrets-in-YAML/secrets-in-reports, **no** face media over MQTT, **no** custom
runtime bridge, and **no** modification to Ring native automations. ✓

---

## Status flags

- `BROKER_PLACEMENT_DECISION = YES` → `SELECTED_BROKER_LOCATION = HOME_ASSISTANT_PI`
- `FRIGATE_PRODUCTION_MQTT_CONFIG = PRIOR_EVIDENCE_ONLY`
- `RING_SECURITY_PATH_DEPENDENT_ON_MQTT = NO`
- `RING_SECURITY_PATH_DEPENDENT_ON_FRIGATE = NO`
- `SECONDARY_PERSON_DEDUP = PROPOSED_NOT_IMPLEMENTED`
- `BROKER_PUBLIC_INTERNET_EXPOSURE = NO`
- `SAFE_TO_BEGIN_MQTT_DEPLOYMENT = NO` (requires explicit authorization per phase)
- `SAFE_TO_BEGIN_LIVE_IMPLEMENTATION = NO`
