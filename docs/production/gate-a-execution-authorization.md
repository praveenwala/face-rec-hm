# Gate A — Production Read-Only Capture: Execution Authorization

**Feature**: [Front Door Person Identification](../../specs/001-front-door-person-identification/spec.md)
**Status**: AUTHORIZATION / PLANNING ONLY — Gate A has **not** been executed; production has
**not** been contacted; `A1` has **not** run.
**Companion**: [gate-a-preparation.md](gate-a-preparation.md) ·
[live-ha-integration-preflight.md](live-ha-integration-preflight.md) ·
[production-deployment.md](production-deployment.md)

> This document defines the exact, bounded authorization for the future **read-only** Gate A
> capture. It authorizes nothing to run now. No production connection, no HA/Frigate/Ring
> change, no mapping install, no reload/restart, no MQTT publish.

---

## Standing blocker

`PRODUCTION_ACCESS_METHOD_IDENTIFIED = PARTIAL` — **ACCESS_BLOCKER = ACTIVE.**

The production Pi is unreachable from this environment and no approved read-only access
method / credential boundary has been established. The blocker may be cleared **only** by
fresh, direct production evidence gathered at `A1` — never inferred from candidate methods,
documentation, dev HA, or prior screenshots/logs.

`ACCESS_BLOCKER_MUST_CLEAR_BEFORE_A2 = YES`.

---

## Authorization boundary

The future authorization permits **only** these steps, in order, and nothing else:

`A1` connectivity/access boundary · `A2` HA version/info · `A3` config root/layout ·
`A4` include/automation layout · `A5` Ring automation read-only capture ·
`A6` Ring entity/state verification · `A7` MQTT integration status ·
`A8` bounded Frigate MQTT subscription · `A9` mapping destination/permissions ·
`A10` deployment method availability · `A11` reload semantics · `A12` backup target list ·
`A13` no-change verification · `A14` sanitized report.

Prohibited: anything outside A1–A14; any write/mutation; any reload/restart; any mapping
install; any MQTT publish; any credential exposure; any access-enabling install/config
change; any ad-hoc command outside the reviewed allowlist.

---

## A1 — Hard gate

`A2`+ may proceed **only if ALL** are true at `A1`:
- production Pi or approved HA read-only endpoint reachable
- access method already exists
- using it requires **no** production configuration change
- **no** service must be installed/enabled
- credential supplied **out-of-band**
- credential **not printed/logged**
- read-only command execution is possible
- command safety is understood

If ANY fails → `GATE_A_STOPPED_AT_A1 = YES`, `ACCESS_BLOCKER = ACTIVE`, **STOP**, no
improvisation, no production file reads.

`A1_HARD_GATE_DEFINED = YES`.

---

## Approved access methods (must already exist)

Existing HA SSH add-on/terminal; existing LAN SSH; existing Samba (read/metadata where
safe); HA REST/WebSocket read-only inspection; already-enabled Supervisor/Terminal console.

**Not allowed:** installing an SSH add-on; enabling SSH; exposing a new port; modifying
firewall; creating a new user; generating/storing new credentials in the repo; weakening
authentication.

---

## Credential handling (hard rule)

Credentials are supplied **out-of-band only**. Never: print a password/token; echo a secret;
intentionally place a secret in shell history; place a secret in the repo/report/logs/committed
docs. If a command would expose a credential to satisfy its own invocation → **STOP**.
`CREDENTIAL_BOUNDARY_DEFINED = YES`.

---

## Read-only command allowlist

Basic reachability (`nc`/`ping`); `curl` **GET** only; HA info GET (`ha core/os/supervisor
info`); `pwd`, `ls`, `find` (no mutation flags), `cat`, `sed -n`, `grep`, `stat`, `id`,
`whoami`; read-only HA state/entity/automation inspection; `mosquitto_sub`; read-only log
inspection; read-only `git status`. Every executed command must be pre-classified
**READ_ONLY**; no command outside the reviewed set may be added ad hoc.
`READ_ONLY_ALLOWLIST_DEFINED = YES`.

## Mutation denylist (any occurrence → STOP)

`rm`, `rmdir`, `mv`, `cp` into production, `touch`, `mkdir`, `chmod`, `chown`, `sed -i`,
`tee`/write redirection, `truncate`, `dd`, `rsync`/`scp` to production, `git
checkout/reset/clean`, HA restart/reload, automation reload, service calls, entity toggles,
automation triggers, `mosquitto_pub`, HTTP POST/PUT/PATCH/DELETE, Frigate/Ring/enrollment
mutation. `MUTATION_DENYLIST_DEFINED = YES`; `MUTATING_COMMANDS_PRESENT = NO`.

---

## Per-step execution safety
- `A1` reachability + access-method confirmation only; no production file reads until A1 passes
- `A2` read-only version/status only
- `A3` list/read metadata; no writes
- `A4` targeted reads only; never dump `secrets.yaml`
- `A5` targeted Ring automation capture only; no automation execution
- `A6` GET/read only; no service calls
- `A7` inspect MQTT connected state/config only
- `A8` **subscribe only**, bounded timeout, no publish
- `A9` inspect dirs/files/permissions only; no `mkdir`/`touch`/`chmod`/`chown`
- `A10` determine what already exists; do not test by uploading
- `A11` determine required reload from target config; do not reload
- `A12` list future backup targets only; do not create backups
- `A13` prove nothing changed
- `A14` sanitize all production evidence

---

## MQTT observation

`frigate/available` + `frigate/events`; **subscribe-only**; bounded timeout; no daemon; no
retained sensitive payload file; **no publish**. A no-event window = `NO_EVENT_OBSERVED`, not
an automatic contract failure. `MQTT_SUBSCRIBE_ONLY_ENFORCED = YES`.

---

## Mapping / transfer / reload decision gates
- `MAPPING_DEPLOYMENT_PATH_DEFINED = YES` only after `A9` confirms actual config root +
  include structure + include-compatible directory + permissions/ownership + rollback-safe
  location; until then **PARTIAL**.
- `MAPPING_TRANSFER_METHOD_DEFINED = YES` only after `A10` identifies an **already-existing**
  mechanism (SSH/SCP, Samba, controlled HA file access, or another already-enabled local
  method); no upload/write test permitted; until then **PARTIAL**.
- `HA_INCLUDE_RELOAD_BEHAVIOR_TARGET_CONFIRMED = YES` only if `A11` target evidence supports a
  classification (`AUTOMATION_RELOAD_SUFFICIENT` / `FULL_CONFIG_RELOAD_REQUIRED` /
  `FULL_HA_RESTART_REQUIRED` / `UNKNOWN`); the reload itself is never performed. Until then
  **NO**. `TARGET_RELOAD_CONFIRMATION_GATE_DEFINED = YES`.

---

## Ring safety requirement (fresh verification at Gate A)

`A5`/`A6` must freshly verify `event.front_door_ding` → existing Ring automation and
`event.front_door_motion` → existing Ring automation remain independent from Frigate / face
recognition / relationship mapping / identity normalization. Target
`RING_SECURITY_PATH_DEPENDENT_ON_AI = NO`; currently PRIOR_EVIDENCE_ONLY (not freshly
verified). If they cannot be freshly read, report PRIOR_EVIDENCE_ONLY, not YES.

---

## Evidence classification

`FRESHLY_VERIFIED` · `PRIOR_EVIDENCE_ONLY` · `UNVERIFIED` · `BLOCKED`. A fact becomes
`FRESHLY_VERIFIED` only when directly observed during Gate A; never inferred from dev HA,
docs, prior screenshots, or old logs.

---

## Privacy

No passwords/tokens/broker credentials/`secrets.yaml` values/full `.storage` dumps/full MQTT
payloads/household UUIDs (unless explicitly approved)/biometric media/crops/clips/embeddings/
real generated mapping/private DB content in committed docs. `!secret` **key names** only.
Synthetic names in committed examples.

---

## No-change proof (Gate A must end proving)

no production files modified; no files created; no permission changes; no HA reload; no HA
restart; no automation triggered; no MQTT publish; no Frigate mutation; no Ring mutation; no
mapping installed → `LIVE_HA_UNCHANGED = YES`. `NO_CHANGE_PROOF_REQUIRED = YES`.

---

## Future Gate A execution report format (populated verbatim at execution)

```
FEATURE 001 — GATE A PRODUCTION READ-ONLY CAPTURE REPORT

A1 ACCESS GATE: Pi reachable / HA reachable / access method / method already existed /
  credentials out-of-band / configuration change required / A1 result / GATE_A_STOPPED_AT_A1
HOME ASSISTANT: Core version / OS version / Supervisor version / config root / evidence class
CONFIG: configuration.yaml / include structure / automation storage / include files /
  helper dirs / evidence class
RING AUTOMATIONS: doorbell found+trigger+conditions+actions+mode / motion found+trigger+
  conditions+actions+cooldown / AI dependency / evidence class
ENTITIES: event.front_door_ding / event.front_door_motion / notify.mobile_app_pk_world /
  evidence class
MQTT: integration state / broker connected / credentials exposed / publish performed
FRIGATE MQTT: available / events / bounded subscription / lifecycle / sub_label /
  sub_label_score / evidence class
MAPPING: exact path / path basis / owner-group / mode / include-compatible / path defined
TRANSFER: method / already available / auth boundary / atomic feasible / rollback feasible /
  transfer defined
RELOAD: include consumer / required future reload / target evidence / target confirmed /
  reload performed
BACKUP TARGETS: files / full HA backup recommended
PRIVACY: secrets printed / private payload persisted / biometric captured / sanitized only
NO-CHANGE: files modified/created / permissions changed / HA reloaded/restarted /
  automations triggered / MQTT published / Frigate/Ring modified / mapping installed
Final flags: GATE_A_PRODUCTION_READ_ONLY_CAPTURE / GATE_A_STOPPED_AT_A1 /
  PRODUCTION_PI_REACHABLE / PRODUCTION_ACCESS_METHOD_IDENTIFIED / ACCESS_BLOCKER /
  LIVE_CONFIG_LAYOUT_FRESHLY_VERIFIED / EXISTING_RING_AUTOMATIONS_FRESHLY_VERIFIED /
  RING_SECURITY_PATH_DEPENDENT_ON_AI / MQTT_INTEGRATION_FRESHLY_VERIFIED /
  FRIGATE_MQTT_FRESHLY_VERIFIED / MAPPING_DEPLOYMENT_PATH_DEFINED /
  MAPPING_TRANSFER_METHOD_DEFINED / HA_INCLUDE_RELOAD_BEHAVIOR_TARGET_CONFIRMED /
  PRODUCTION_BACKUP_TARGETS_DEFINED / MUTATING_ACTIONS_PERFORMED / LIVE_HA_UNCHANGED /
  SAFE_TO_CHECKPOINT_GATE_A / SAFE_TO_BEGIN_LIVE_IMPLEMENTATION / SAFE_TO_MODIFY_LIVE_HOME_ASSISTANT
```
