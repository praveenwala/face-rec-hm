# MQTT State Reconciliation — Post-Install (Blocker 1, MQTT-B3 deviation)

**Feature**: [Front Door Person Identification](../../specs/001-front-door-person-identification/spec.md)
**Status**: STATE RECONCILIATION / DOCUMENTATION ONLY. This record reconciles project state with
production changes that **actually occurred** during operator-assisted PRE-B3-A. No further
production mutation is authorized here.
**Supersedes (for CURRENT state only):** the point-in-time "current state" snapshots in
[gate-a-results.md](gate-a-results.md) §MQTT and [mqtt-deployment-runbook.md](mqtt-deployment-runbook.md) §1.
Those documents remain historically accurate as of their capture; this record is the current truth.

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

- `FULL_HA_BACKUP_TAKEN_BEFORE_BROKER_INSTALL = NO` (deviation)
- `FULL_HA_BACKUP_OF_CURRENT_STATE_TAKEN = NO`
- **Next required gate: PRE-B3-B — full HA backup of the current healthy MQTT-enabled state.**
  No further production mutation (ACLs, Frigate config, mapping, automations) until it is taken
  and verified.

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
