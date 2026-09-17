# MQTT State Reconciliation — Post-Install (Blocker 1, MQTT-B3 deviation)

**Feature**: [Front Door Person Identification](../../specs/001-front-door-person-identification/spec.md)
**Status**: STATE RECONCILIATION / DOCUMENTATION ONLY. This record reconciles project state with
production changes that **actually occurred** during operator-assisted PRE-B3-A. No further
production mutation is authorized here.
**Supersedes (for CURRENT state only):** the point-in-time "current state" snapshots in
[gate-a-results.md](gate-a-results.md) §MQTT and [mqtt-deployment-runbook.md](mqtt-deployment-runbook.md) §1.
Those documents remain historically accurate as of their capture; this record was the current
truth as of 2026-09-14.

> **SUPERSEDED for CURRENT state** (2026-09-17): §4 below ("Blocker 1 NOT fully resolved" /
> `FRIGATE_MQTT_CONNECTED_TO_PRODUCTION = NO`) is no longer current. Frigate is now connected to
> the production broker, the normalization automation is deployed/enabled and consuming real
> `frigate/events`, and the generated relationship mapping now exists on production — see
> [mqtt-b5-production-verification-2026-09-17.md](mqtt-b5-production-verification-2026-09-17.md).
> §1–3 and §5 (broker install, backup, key-rotation history) remain accurate as historical fact
> and are unaffected by this update.

---

## 1. Deviation (recorded honestly; history not rewritten)

During operator-assisted PRE-B3-A read-only inspection, the **operator manually installed the
official Mosquitto Broker add-on** (and then configured the HA MQTT integration + ran a local
loopback test) **before the planned backup gate (PRE-B3-B)**. This **crossed the read-only
boundary** that PRE-B3-A defined.

- `BROKER_INSTALLATION_DEVIATION_RECORDED = YES`
- `FULL_HA_BACKUP_TAKEN_BEFORE_BROKER_INSTALL = NO` (a backup did **not** exist before install)
- This is documented, not relabeled or hidden. The prior runbook/Gate A "current state"
  snapshots (Mosquitto NOT installed / HA MQTT absent) were true at capture; they are now
  superseded by §3 below.

Consequence: the required backup gate is **not** skipped — it is re-scoped to a **current-state**
backup (PRE-B3-B) that must be taken and verified **before any further production mutation**.

## 2. Evidence source

- **TARGET_OBSERVED** (operator-assisted, read-only verification at the Pi): broker install
  state/version, listeners, auth flags, HA MQTT integration status, local loopback roundtrip.
- **OFFICIAL_DOCUMENTATION** (visible in the add-on): auth backend options, ACL/customize model.
- **INFERENCE:** none used for the flags below.

## 3. Current verified MQTT state (TARGET_OBSERVED — supersedes prior snapshots)

### Broker
- `MOSQUITTO_INSTALLED = YES` · `MOSQUITTO_RUNNING = YES`
- `MOSQUITTO_APP_VERSION = 7.1.1` · `MOSQUITTO_ENGINE_VERSION = 2.1.2`
- `MOSQUITTO_START_ON_BOOT = YES`
- `auth_api = true`; username/password auth enabled; **SSL currently disabled**;
  `require_certificate = false`; **anonymous access not supported by the app**
- listener ports active: 1883/tcp (MQTT), 1884/tcp (MQTT/WebSocket), 8883/tcp (MQTT+SSL),
  8884/tcp (MQTT/WebSocket+SSL); running listeners observed on IPv4/IPv6 **1883** and **1884**

### Auth / users
- `MQTT_AUTH_BACKEND = MIXED` — HA users may authenticate; optional local Mosquitto users also
  supported. `MQTT_CREDENTIAL_MECHANISM_DEFINED = YES`.
- dedicated non-admin client identities are possible; **Frigate must NOT use HA admin creds**
  (`FRIGATE_USES_ADMIN_HA_CREDENTIALS = NO` — target requirement).
- `ANONYMOUS_ACCESS_SUPPORTED = NO`.

### ACL
- `MOSQUITTO_TOPIC_ACL_CAPABILITY = SUPPORTED`; `CUSTOM_MOSQUITTO_CONFIG_REQUIRED_FOR_ACL = YES`.
- `customize.active = false` (default customize folder `mosquitto`); example ACL paths
  `/share/mosquitto/acl.conf`, `/share/mosquitto/accesscontrollist`.
- Internal users `homeassistant` and `addons` must retain unrestricted readwrite when ACLs are
  enabled. `ACL_CONFIGURED = NO` (planned least-privilege Frigate account remains future work).

### Home Assistant MQTT integration
- `HA_MQTT_INTEGRATION_CONFIGURED = YES` · `HA_MQTT_STATUS = ONLINE` · 0 devices / 0 entities.

### Local loopback test (temporary, non-retained)
- topic `homeassistant/test`, payload `hi`, QoS 0, retain **false**; HA subscribed + published +
  received immediately. `MQTT_LOCAL_PUBLISH = PASS` · `MQTT_LOCAL_SUBSCRIBE = PASS` ·
  `MQTT_LOCAL_ROUNDTRIP = PASS`. No retained test state created. No credentials recorded.

### Network / TLS
- `MQTT_LISTENER_BEHAVIOR_DEFINED = YES` · `MQTT_LAN_ACCESS_SUPPORTED = YES`
- `BROKER_PUBLIC_INTERNET_EXPOSURE = NO` · `ROUTER_PORT_FORWARDING_REQUIRED = NO`
- `TLS_REQUIRED = NO` · `TLS_DECISION_TARGET_COMPATIBLE = YES` (authenticated plaintext 1883 on
  trusted LAN is supported; SSL listeners exist if later required)

## 4. Still unverified — Blocker 1 NOT fully resolved

The HA/broker side is operational, but **end-to-end Frigate transport is not verified**:
- `PRODUCTION_FRIGATE_MQTT_CONFIG = UNVERIFIED`
- `FRIGATE_MQTT_CONNECTED_TO_PRODUCTION = NO`
- `FRIGATE_AVAILABLE_TOPIC_VERIFIED = NO` · `FRIGATE_EVENTS_TOPIC_VERIFIED = NO`
- no Frigate MQTT credentials created; no Frigate MQTT config modified.

Blocker 1 (MQTT/Frigate transport) is **partially cleared** (broker + HA client verified) but
remains **open** until Frigate connects and `frigate/available` + `frigate/events` are observed.

## 5. Backup state (hard gate)

- `FULL_HA_BACKUP_TAKEN_BEFORE_BROKER_INSTALL = NO` (deviation — historical fact, unchanged)
- `FULL_HA_BACKUP_OF_CURRENT_STATE_TAKEN = YES` — **PRE-B3-B completed & verified (2026-09-14)**;
  see §5a below.

### 5a. PRE-B3-B — Current-state HA backup (operator-executed; verified via HA UI)

`PRE_B3_B_CURRENT_STATE_BACKUP = PASS` · `BACKUP_VERIFIED_COMPLETE = YES`.

| Fact | Value |
|---|---|
| name | Automatic backup 2026.9.1 |
| type | Automatic |
| created | 2026-09-14 3:34 PM |
| size | 19.42 MB |
| encrypted | YES |
| location(s) | 1 — This system |

Contents (only what the HA restore/details UI directly showed):
- Home Assistant: settings & history, version **2026.9.1**; SSL certificates included
- Apps: **Mosquitto broker 7.1.1**; **Terminal & SSH 10.4.0**

No restore was performed. **Post-backup health:** HA running, Mosquitto running,
`HA_MQTT_STATUS_AFTER_BACKUP = ONLINE`; no restart performed.

Post-backup MQTT roundtrip (temporary, non-retained): topic `homeassistant/test`, payload
`hi`, QoS 0, retain **false** — received immediately. `MQTT_POST_BACKUP_PUBLISH = PASS` ·
`MQTT_POST_BACKUP_SUBSCRIBE = PASS` · `MQTT_POST_BACKUP_ROUNDTRIP = PASS`. No retained state.

### 5b. SECURITY — backup encryption key exposure (separate remediation gate)

During operator interaction the backup **encryption/recovery key was accidentally exposed
outside the HA UI**. The key is **not** recorded here or anywhere in the repo (no key, no
substring, no derived credential, no screenshot containing it).

- `BACKUP_ENCRYPTION_KEY_EXPOSURE_RECORDED = YES`
- `BACKUP_KEY_ROTATION_REQUIRED = YES`

**REMEDIATION COMPLETED & VERIFIED (2026-09-14, operator-executed via HA UI):**
`BACKUP_KEY_REMEDIATION_EXECUTION = PASS` · `BACKUP_KEY_CHANGE_COMPLETED = YES`.

- The backup encryption key was **changed** (HA UI). Per HA 2026.9.x semantics, the new key
  applies to **future** backups only; the previously-created backup stayed tied to the old
  (exposed) key — so it was **deleted** after a new protected backup was verified.
- **New backup (under the new key):** name `Automatic backup 2026.9.1`; created 2026-09-14
  4:20 PM; size **19.58 MB**; encrypted YES; contents (UI-verified): Home Assistant + settings
  & history (2026.9.1) + SSL certificates; **Mosquitto broker 7.1.1**; **Terminal & SSH 10.4.0**.
  `NEW_BACKUP_CREATED = YES` · `NEW_BACKUP_VERIFIED_COMPLETE = YES` · `NEW_BACKUP_STILL_PRESENT = YES`.
- **Old exposed-key backup deleted:** the prior `Automatic backup 2026.9.1` (**19.42 MB**,
  created before remediation) was deleted **after** the new backup was verified.
  `OLD_EXPOSED_KEY_BACKUP_DELETED = YES`. (Records only the local deletion; makes no claim about
  copies that may exist elsewhere.)
- **Post-change health:** HA running; local MQTT roundtrip re-verified — topic `homeassistant/test`,
  payload `hi`, QoS 0, retain **false** — received immediately.
  `MQTT_POST_KEY_CHANGE_PUBLISH/SUBSCRIBE/ROUNDTRIP = PASS`; no retained state.
- Keys (old or new) are **not** recorded anywhere in the repo. `BACKUP_KEY_PRESENT_IN_REPO = NO`.
  `SAFE_TO_ROTATE_BACKUP_KEY` gate is now satisfied/closed.

## 6. Ring safety (unchanged)

- `RING_SECURITY_PATH_DEPENDENT_ON_MQTT = NO` · `RING_SECURITY_PATH_DEPENDENT_ON_FRIGATE = NO`
- `NATIVE_RING_NOTIFICATION_IMPACT = NONE`. Existing Ring ding/motion automations unchanged; the
  MQTT broker install does not sit in their trigger/action path.

## 7. Other blockers (unchanged; out of scope)

- `MAPPING_DEPLOYMENT_PATH_DEFINED = PARTIAL`
- `TARGET_MAPPING_RELOAD_SEMANTICS = UNKNOWN`

## 8. Not done in this phase

No production contact; no MQTT users/ACLs created; customize not enabled; Mosquitto options
unchanged; Frigate unchanged; no further MQTT publish/subscribe; Ring unchanged; mapping not
installed; no HA automation changes; no reload/restart; **backup not taken**.
