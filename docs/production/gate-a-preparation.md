# Gate A — Production Read-Only Capture: Preparation Plan

**Feature**: [Front Door Person Identification](../../specs/001-front-door-person-identification/spec.md)
**Status**: PREPARATION / PLANNING ONLY — Gate A has **not** been executed; production has
**not** been contacted.
**Companion**: [live-ha-integration-preflight.md](live-ha-integration-preflight.md) ·
[production-deployment.md](production-deployment.md)

> This document prepares the future **read-only** Gate A capture on the production Raspberry
> Pi Home Assistant. It authorizes nothing. No production connection, no HA/Frigate/Ring
> change, no mapping install, no reload/restart, no MQTT publish.

---

## Access blocker (ACTIVE)

`PRODUCTION_ACCESS_METHOD_IDENTIFIED = PARTIAL` — **ACCESS_BLOCKER = ACTIVE.**

The actual production Pi access method, LAN reachability, and a read-only credential boundary
are **unresolved**. The repo does not commit a specific access mechanism (production-
deployment.md defers the deployment mechanism to Phase 4); this development environment cannot
reach the Pi. Access must be proven at Gate A step **A1** and must satisfy ALL of:

- production Pi reachable
- an approved **read-only** access method identified
- credential/token boundary established, supplied **out-of-band**
- credentials never printed into logs/docs/history
- read-only commands can run without changing production

Do **not** infer access from prior docs. Do **not** mark the access method resolved based on
candidate methods alone.

---

## Read-only boundary

**Allowed:** reachability checks; version/info reads; file listings; targeted file reads;
entity/state inspection (read); automation inspection (read); permission/ownership inspection;
MQTT **subscribe-only** observation; safe log reading.

**Prohibited:** file writes; `chmod`/`chown`; `mkdir`/`touch`/`cp`/`mv`/`rm`; config edits;
write-capable HA service calls; automation triggering; entity toggling; `mosquitto_pub`; HA
reload/restart; Frigate/Ring/enrollment mutation.

`MUTATING_COMMANDS_PRESENT = NO`.

---

## Prepared execution order (do NOT execute)

`A1` connectivity/access boundary → `A2` HA version/info → `A3` config root/layout →
`A4` include/automation layout → `A5` Ring automation read-only capture →
`A6` Ring entity/state verification → `A7` MQTT integration status →
`A8` bounded Frigate MQTT subscription → `A9` mapping destination/permissions →
`A10` deployment method availability → `A11` reload semantics → `A12` backup target list →
`A13` no-change verification → `A14` Gate A report.

---

## Approved read-only command inventory (reviewed before any execution)

Every command below is classified **READ_ONLY**. Commands that depend on the chosen access
method (SSH shell vs REST/WebSocket) are marked *conditional*. None are run in preparation
or checkpoint.

| Step | Command (representative) | Purpose | Mutation risk | Class |
|---|---|---|---|---|
| A1 | `nc -z -w3 <pi> 8123` / `nc -z -w3 <pi> 22` | reachability | none | READ_ONLY |
| A2 | *SSH:* `ha core info` / `ha os info` / `ha supervisor info` — *REST:* `curl -sS -H "Authorization: Bearer $TOKEN" http://<pi>:8123/api/config` (GET) | HA Core/OS/Supervisor version + `config_dir` | none (token never printed) | READ_ONLY |
| A3 | `ls -la /config` ; `sed -n '1,200p' /config/configuration.yaml` | config root + include directives | none | READ_ONLY |
| A4 | `grep -nE '!include|!include_dir|packages' /config/configuration.yaml` ; `ls -la /config/automations* /config/packages 2>/dev/null` | automation storage model | none | READ_ONLY |
| A5 | `sed -n '1,400p' /config/automations.yaml` *or* GET `/api/config/automation/config/<id>` *or* targeted `.storage/automations` read | verbatim ding + motion trigger/condition/action/mode/cooldown/notify | none | READ_ONLY |
| A6 | `curl -sS -H "Authorization: Bearer $TOKEN" http://<pi>:8123/api/states/event.front_door_ding` (and `…front_door_motion`) | entity existence + state | none | READ_ONLY |
| A7 | GET `/api/states` (filter `notify.mobile_app_pk_world`) / MQTT integration status (read) | notify target + MQTT integration/broker connected | none | READ_ONLY |
| A8 | `mosquitto_sub -h <broker> -p <port> -t 'frigate/available' -t 'frigate/events' -W 60 -v` (auth via env, not echoed) | observe availability + one event lifecycle | none — **subscribe only** | READ_ONLY |
| A9 | `ls -la /config` ; `stat -c '%U %G %a %n' /config /config/helpers 2>/dev/null` ; `id` | candidate include destination + owner/group/mode + current user | none | READ_ONLY |
| A10 | `ha addons info`/list (read) or Settings inspection | which of SSH/SCP, Samba, File Editor is available | none | READ_ONLY |
| A11 | derive from A3–A5 which domain/automation consumes the include | determine required reload | none — **no reload performed** | READ_ONLY |
| A12 | enumerate exact files to back up (from A3–A5) | backup target list (no backup created) | none | READ_ONLY |
| A13 | re-`stat` candidate files (mtime) | prove nothing was modified during Gate A | none | READ_ONLY |

Reject any command whose behavior is ambiguous or potentially mutating.

---

## A1 — Access boundary (first step; STOP conditions)

A1 must STOP (report blocker, do not improvise) if access would require: installing an SSH
add-on/enabling a new service; changing firewall/network/HA config; exposing a password/token;
enabling write access; or otherwise weakening security. A1 only determines reachability + an
approved read-only method + an out-of-band credential boundary.

---

## MQTT observation plan

- topics: `frigate/available`, `frigate/events`; **subscribe-only**, bounded `-W 60`.
- no retained subscription service; no broker mutation; **no `mosquitto_pub`**; no synthetic
  production event; no full sensitive payload retention.
- record only: lifecycle, `event_id`, camera, label, presence-of-`sub_label`,
  presence-of-`sub_label_score`. `MQTT_OBSERVATION_IS_SUBSCRIBE_ONLY = YES`.

---

## Mapping destination — decision criteria (no final path yet)

Criteria: inside HA config tree; `!include`-compatible; private/local; writable via an
approved deployment method; no secret/public exposure; supports atomic temp-file+rename;
simple rollback; no runtime daemon. Candidate **example only** (NOT chosen):
`/config/helpers/relationship_mapping.generated.yaml` — the real path is assigned only after
Gate A A9 confirms the production layout. `MAPPING_DECISION_CRITERIA_DEFINED = YES`;
`MAPPING_DEPLOYMENT_PATH_DEFINED = PARTIAL`.

## Transfer method — candidates only (no final method yet)

Priority: (1) SSH/SCP with atomic temp+rename; (2) Samba validated local-copy; (3) HA File
Editor manual; (4) other approved local mechanism. No daemon/sync watcher. Final method
chosen only after Gate A A10 proves availability on the target.
`MAPPING_TRANSFER_METHOD_DEFINED = PARTIAL`.

## Target reload — confirmation planned (not performed)

Known: `!include` resolves at config/automation **load**; a mapping change requires reloading
the consuming domain or restarting HA. Gate A A11 will classify the target as
`AUTOMATION_RELOAD_SUFFICIENT` / `FULL_CONFIG_RELOAD_REQUIRED` / `FULL_HA_RESTART_REQUIRED` /
`UNKNOWN`. `TARGET_RELOAD_CONFIRMATION_PLANNED = YES`;
`HA_INCLUDE_RELOAD_BEHAVIOR_TARGET_CONFIRMED = NO`. No reload is performed in preparation,
checkpoint, or (for the reload itself) Gate A.

---

## Backup targets (enumerate at A12; create none now)

`configuration.yaml` (if touched); the automation include file to be modified; the generated
mapping destination; current Ring automation definitions; any relevant package/include file.
Prefer a full HA OS backup on the Pi. No backup is created during preparation.

---

## Stop conditions (Gate A)

Pi unreachable; HA unreachable; unsafe credential boundary; access requires a config change;
only write-capable access available; target architecture differs materially from preflight;
MQTT observation would require publish; candidate config files cannot be safely identified; HA
appears unhealthy; command safety cannot be established. `STOP_CONDITIONS_DEFINED = YES`.

---

## Privacy

Never print `secrets.yaml` contents (metadata/listing only); record `!secret` **key names**
only, never resolved values; no biometric media/crops/clips/embeddings captured; sanitize
household names/UUIDs/unnecessary device IDs in committed docs (use synthetic examples); do
not commit raw `.storage` dumps or full MQTT payloads; prefer targeted extraction.

---

## Ring independence (to be freshly verified at Gate A)

Gate A A5/A6 must confirm `event.front_door_ding` → existing Ring automation and
`event.front_door_motion` → existing Ring automation reference **no** Frigate / face
recognition / identity helper / generated mapping. Expected `RING_SECURITY_PATH_DEPENDENT_ON_AI
= NO`; currently PRIOR_EVIDENCE_ONLY (not freshly verified).

---

## Production facts — still NOT freshly verified

HA Core version; HA OS/Supervisor version; config root; `configuration.yaml` include layout;
automation storage model; Ring ding automation; Ring motion automation; Ring notification
target; MQTT integration/broker state; Frigate topics; mapping destination;
permissions/ownership; transfer method; target reload behavior. None may be upgraded to
FRESHLY_VERIFIED before Gate A execution.

---

## No-change verification (this preparation + checkpoint)

no production connection; no Pi commands executed; no HA API call; no HA file access; no MQTT
subscription; no MQTT publish; no HA reload/restart; no mapping deployment; Frigate unchanged;
Ring unchanged.
