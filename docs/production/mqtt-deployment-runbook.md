# MQTT Deployment Runbook — Blocker 1 (MQTT-B2 Preparation)

**Feature**: [Front Door Person Identification](../../specs/001-front-door-person-identification/spec.md)
**Status**: PREPARATION ONLY (MQTT-B2) — an operator-ready procedure for the future MQTT-B3/B4/B5
phases. **No production action is authorized here.** No install, no config, no credentials, no
Frigate/Ring change, no MQTT publish/subscribe.
**Companion**: [mqtt-transport-plan.md](mqtt-transport-plan.md) · [gate-a-results.md](gate-a-results.md) ·
[production-deployment.md](production-deployment.md) ·
[mqtt-events contract](../../specs/001-front-door-person-identification/contracts/mqtt-events.md)

> Decision (MQTT-B1): broker = **Mosquitto add-on on the HA Pi**. This runbook prepares its
> deployment. Every mutating phase (B3/B4/B5) requires **separate explicit authorization** and
> must STOP before the next.

---

## 1. Current verified production state (do not upgrade here)

- HA Core 2026.9.1 · HA OS 18.2 · Supervisor 2026.09.0 · machine `raspberrypi3-64`
- config root `/homeassistant`; `/config` → `/homeassistant`
- Mosquitto Broker add-on: **available, NOT installed**
- HA MQTT integration: **absent**
- existing Ring ding/motion automations: independent (Gate A)
- Terminal/SSH access available; File Editor + Samba **not installed**; no `helpers/` dir
- production MQTT/Frigate transport: **UNVERIFIED**
- `live HA contacted (this phase): NO`

## 2. MQTT-B3 — Broker deployment procedure (future; do NOT execute)

Operator steps (HA UI preferred, most auditable on HA OS):
1. **Record pre-state:** Settings → Add-ons list; current Supervisor/Core health; take a full
   HA backup (see §backup).
2. Install the official **Mosquitto broker** add-on: Settings → Add-ons → Add-on Store →
   "Mosquitto broker" → Install.
3. Confirm install success: add-on shows "Installed"; add-on log shows broker started with no
   errors.
4. **Startup behavior / add-on options require runtime confirmation** on HA OS 18.2 /
   Supervisor 2026.09.0 (auto-start on boot, default listener, `logins`/ACL option schema).
   `TARGET_BEHAVIOR_REQUIRES_RUNTIME_CONFIRMATION = YES` — do not assume older HA behavior.
5. **STOP** after broker is installed + healthy. Do not configure the HA MQTT integration in B3.

- app identifier: the official "Mosquitto broker" add-on (exact slug to confirm at runtime,
  historically `core_mosquitto`; confirm on target, do not assume).

## 3–5. Credential model + HA-vs-broker-user decision (no credentials created)

Two least-privilege clients (placeholders only):

| Role | Purpose | Publish | Subscribe | Discovery topics | Wildcards | R/W |
|---|---|---|---|---|---|---|
| **FRIGATE_MQTT_CLIENT** (`<FRIGATE_MQTT_USER>`/`<FRIGATE_MQTT_PASSWORD>`) | Frigate → broker event publish | `frigate/#` (or `frigate/events`,`frigate/available`) | none required for Feature 001 | no | only within `frigate/` prefix | publish (write) |
| **HOME_ASSISTANT_MQTT_CLIENT** (`<HA_MQTT_USER>`/`<HA_MQTT_PASSWORD>`) | HA subscribes to Frigate topics | not required for Feature 001 | `frigate/events`, `frigate/available` | see §10 discovery | no | subscribe (read) |

- **Credential mechanism on the official Mosquitto add-on:** historically the add-on
  authenticates against **Home Assistant users** by default and also supports add-on-local
  `logins:` users; **per-topic ACL granularity via the add-on is limited** and its exact schema
  on this target version must be confirmed. Therefore
  **`MQTT_CREDENTIAL_MECHANISM = REQUIRES_TARGET_CONFIRMATION`** (resolve before B3). If the
  add-on cannot enforce sufficiently granular ACLs, document that and either accept
  authenticated-but-coarse access on the trusted LAN or use dedicated local users — do not
  invent ACL behavior.
- No usernames/passwords are generated in this phase.

## 6. Secret storage (no files created here)

- **Home Assistant side:** the HA MQTT integration stores its credential in HA's config-entry
  storage (`.storage`, not Git). If any YAML reference is ever needed, use `!secret` →
  `secrets.yaml` (gitignored), never inline.
- **Frigate side:** prefer Frigate's supported secret/env mechanism (e.g.
  `password: "{FRIGATE_MQTT_PASSWORD}"` sourced from an env var / Frigate secret) rather than
  plaintext in the tracked config. The real Frigate config lives on the AI host and is
  gitignored for production; **never commit real credentials**.
- Never: in Git, in committed YAML, in reports, in screenshots, or (avoidably) in shell history.

## 7. Network design

- endpoint: `mqtt://<HOME_ASSISTANT_LAN_HOST>:1883` (placeholder host — do not hardcode a real
  IP until freshly verified for this purpose)
- listener: LAN interface on the Pi; must be reachable by the Frigate AI host
- `LAN only = YES`; `Internet exposure = NO`; no router port-forwarding; no mDNS dependency
  unless explicitly chosen at deployment
- `MQTT_LISTENER_BEHAVIOR_DEFINED = REQUIRES_TARGET_CONFIRMATION` (the add-on's default listener
  interface/port binding on HA OS must be confirmed at B3)

## 8. TLS decision

- **`TLS_REQUIRED = NO`** for the initial single trusted-LAN deployment.
- Rationale + compensating controls: authenticated clients (no anonymous), LAN-only listener,
  no port-forwarding, local network boundary. Revisit (8883 + TLS) if the LAN is not fully
  trusted or the broker must span segments. Anonymous mode is **never** enabled for convenience.

## 9. MQTT-B4 — HA MQTT integration procedure (future; do NOT execute)

1. Settings → Devices & Services → Add Integration → **MQTT**.
2. Broker host = `<HOME_ASSISTANT_LAN_HOST>` (or `core-mosquitto`/localhost per target),
   port = 1883, username `<HA_MQTT_USER>`, password `<HA_MQTT_PASSWORD>` (out-of-band).
3. Discovery: see §10.
4. Expected state: integration shows **"connected"**.
5. Verify health read-only: integration status connected; observe `frigate/available` via
   Developer Tools → MQTT "Listen to a topic" (no publish).
6. Whether HA auto-discovers its local Mosquitto add-on on this version is **not assumed** —
   confirm at runtime.
7. **STOP** after HA shows connected. Do not modify Frigate in B4.

## 10. Discovery decision

- Feature 001 consumes `frigate/available` + `frigate/events` by explicit subscription; it does
  **not** require HA MQTT **device discovery** for those.
- The official **Frigate HA integration** (if used later) does use discovery/its own topics, but
  that is separate from Feature 001's raw-topic consumption.
- **`MQTT_DISCOVERY_REQUIRED_FOR_FEATURE_001 = NO`** (enable only if the Frigate integration is
  adopted later; do not confuse event-topic subscription with device discovery).

## 11. MQTT-B5 — Frigate MQTT config preparation (Frigate 0.17.2; placeholders only)

```yaml
mqtt:
  enabled: true
  host: <HOME_ASSISTANT_MQTT_HOST>
  port: 1883
  user: <FRIGATE_MQTT_USER>
  password: <FRIGATE_MQTT_PASSWORD>     # via Frigate secret/env, not plaintext tracked
  topic_prefix: frigate
  # client_id: <FRIGATE_CLIENT_ID>      # optional
```

Only fields supported by Frigate 0.17.2 (`enabled`, `host`, `port`, `user`, `password`,
`topic_prefix`, `client_id`). No invented properties.

- `TRACKED_FRIGATE_MQTT_SECTION = PRESENT` — the dev POC `frigate/config/config.yml` has a
  minimal `mqtt: {host: mosquitto, port: 1883, topic_prefix: frigate}` (anonymous, single-host).
- `PRODUCTION_FRIGATE_MQTT_CONFIG = UNVERIFIED` (production runs on the not-yet-selected AI host).
- **STOP** after Frigate config change + Frigate restart; do not begin event validation in B5.

## 12. Topic access matrix

| Topic | Frigate | Home Assistant |
|---|---|---|
| `frigate/available` | publish | subscribe |
| `frigate/events` | publish | subscribe |

- HA needs **no publish** for Feature 001.
- If Frigate itself requires internal broker subscriptions for its own features, that is
  separate from Feature 001 and must not be conflated (scope it explicitly at B5). Do not
  overgrant.

## 13. QoS / retain

| Topic | QoS | Retain | HA handling |
|---|---|---|---|
| `frigate/available` | `REQUIRES_OBSERVATION` (likely retained availability/LWT) | `REQUIRES_OBSERVATION` (likely retained) | treat stale/offline as `Unavailable` |
| `frigate/events` | `FRIGATE_DEFAULT` / `REQUIRES_OBSERVATION` | non-retained (event stream) | dedup by `event_id`; tolerate reconnect/duplicates |

No exact broker semantics invented; confirm by observation at B6.

## 14. MQTT-B6 — validation sequence (read-only; future)

A. Mosquitto add-on healthy → B. HA MQTT integration connected → C. Frigate connected →
D. `frigate/available` observed → E. bounded `frigate/events` observation →
F. person event lifecycle observed → G. `event_id` observed → H. camera/label observed →
I. `sub_label` behavior → J. `sub_label_score` behavior → K. detection `after.score` remains
distinct → L. existing Ring ding/motion notification path still works. Read-only throughout.

## 15. MQTT test-client policy

Prefer least intrusive: **HA Developer Tools → MQTT "Listen to a topic"** (no publish), plus
add-on/Frigate **logs**. If a shell subscriber is needed, use `mosquitto_sub` from the
**existing Terminal/SSH add-on on the Pi** or another already-trusted host — do not install
extra tooling on HA solely for this. Never `mosquitto_pub` to production.

## 16. Backup plan (before MQTT-B3)

- **Full Home Assistant backup/snapshot** on the Pi (preferred).
- Targeted: `configuration.yaml`, `automations.yaml`; Frigate config before MQTT-B5.
- Do not copy `.storage` into Git.

## 17. Rollback

- **B3 (broker):** stop/uninstall the Mosquitto add-on if required.
- **B4 (HA integration):** delete/disable the MQTT integration.
- **B5 (Frigate):** restore prior Frigate config, restart Frigate.
- Throughout: **Ring automations untouched; Ring notifications continue; no mapping dependency.**
  Rolling back AI transport must not affect the native security path.

## 18. Failure safety

| Scenario | Outcome |
|---|---|
| Mosquitto unavailable | AI enrichment lost only; Ring unaffected |
| HA MQTT disconnected | AI enrichment lost only; Ring unaffected |
| Frigate MQTT disconnected / Frigate restarted | events pause; `Unavailable` on `frigate/available`; Ring unaffected |
| AI host offline | AI enrichment lost only; broker (on Pi) + HA + Ring unaffected |
| Pi restarted | whole control plane cycles; Ring resumes with HA; no AI dependency introduced |
| network link fails | AI events stop; Ring path unaffected |

**`NATIVE_RING_NOTIFICATION_IMPACT = NONE`** in all cases.

## 19. Pi 3 resource safety (verify during B3, no monitoring tools installed)

Observe: HA UI responsiveness; Supervisor/add-on health; Mosquitto add-on health; CPU/load and
memory if readily available (`ha` CLI / Supervisor UI); no watchdog restarts; Ring automation
still responsive. Do not install monitoring software for this test.

## 20. Hard gates

`MQTT-B3` install/start broker only → **STOP before HA MQTT config**.
`MQTT-B4` configure HA MQTT integration only → **STOP before Frigate modification**.
`MQTT-B5` configure Frigate MQTT only → **STOP before event validation**.
`MQTT-B6` read-only event/topic validation.
`MQTT-B7` failure isolation / regression (AI down → Ring still works).
`MQTT-B8` documentation/checkpoint. No phase silently proceeds into the next.

## 21. Security risks before B3

| Risk | Classification |
|---|---|
| Credential mechanism / ACL granularity uncertain on target | **BLOCKING_BEFORE_B3** (resolve `MQTT_CREDENTIAL_MECHANISM`) |
| Broker listener/interface behavior on HA OS 18.2 uncertain | CAN_VALIDATE_DURING_B3 (confirm immediately after install, before exposing) |
| HA full backup not yet taken | **BLOCKING_BEFORE_B3** |
| Target add-on startup/options schema unverified | CAN_VALIDATE_DURING_B3 |
| Production Frigate MQTT config unverified | affects B5, not B3 |

`SECURITY_CRITICAL_B3_BLOCKERS = YES` (credential mechanism + backup must be resolved before B3).

---

## Status flags

- `MOSQUITTO_INSTALL_PROCEDURE_DEFINED = YES`
- `MQTT_CREDENTIAL_MECHANISM = REQUIRES_TARGET_CONFIRMATION`
- `MQTT_SECRET_STORAGE_DEFINED = YES`
- `MQTT_LISTENER_BEHAVIOR_DEFINED = REQUIRES_TARGET_CONFIRMATION`
- `TLS_REQUIRED = NO` (trusted-LAN; compensated by auth + LAN-only + no forwarding)
- `MQTT_DISCOVERY_REQUIRED_FOR_FEATURE_001 = NO`
- `FRIGATE_MQTT_CONFIG_SHAPE_DEFINED = YES` · `TRACKED_FRIGATE_MQTT_SECTION = PRESENT` ·
  `PRODUCTION_FRIGATE_MQTT_CONFIG = UNVERIFIED`
- `NATIVE_RING_NOTIFICATION_IMPACT = NONE`
- `SECURITY_CRITICAL_B3_BLOCKERS = YES`
- `SAFE_TO_BEGIN_MQTT_B3 = NO`
