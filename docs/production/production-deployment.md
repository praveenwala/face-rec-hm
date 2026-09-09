# Production Deployment

**Feature**: [Front Door Person Identification](../../specs/001-front-door-person-identification/spec.md)
**Companion documents**: [plan.md](../../specs/001-front-door-person-identification/plan.md) ·
[tasks.md](../../specs/001-front-door-person-identification/tasks.md) ·
[validation-report.md](../../specs/001-front-door-person-identification/validation-report.md) ·
[local-mac-testing.md](../testing/local-mac-testing.md) · [constitution](../../.specify/memory/constitution.md)

> **This document describes the target production architecture. It does not change it.** The
> Raspberry Pi 3 is, and remains, the production Home Assistant control plane — it is **not**
> the production Frigate/face-recognition compute host. Nothing here redesigns that
> constraint (constitution Principles I.1, I.2).

## Architecture

```text
Ring Front Door
        ↓
ring-mqtt (Ring cloud bridge + local on-demand RTSP gateway)
        ↓
go2rtc / RTSP
        ↓
dedicated AI compute host
        ↓
Frigate + person detection + face recognition
        ↓
MQTT
        ↓
Raspberry Pi 3 running Home Assistant
        ↓
iPhone notifications / dashboards / automations
```

This has two separate production components, documented independently below, because they
run on different hosts with different responsibilities and different risk profiles:

- **(A) Raspberry Pi 3** — the existing, already-working Home Assistant control plane.
- **(B) A separate, not-yet-selected production AI compute host** — where Frigate and face
  recognition actually run.

They are never the same machine.

### Frigate version (updated 2026-09-09: 0.15.1 → 0.17.2)

The Mac POC now runs **Frigate `0.17.2`** (current stable as of 2026-09-09). It was upgraded
from `0.15.1` because native face recognition was introduced in Frigate 0.16.0 and the POC's
PD-09 hardware gate (`PD09_PASS`) requires a build that contains the feature. Production MUST
deploy Frigate 0.17.x (or newer stable) — re-pin per constitution VI.3 at deployment time.

**Production note (0.17 breaking change):** go2rtc `exec:`/`echo:`/`expr:` sources are
blocked by default in 0.17 for security. The Mac POC sets
`GO2RTC_ALLOW_ARBITRARY_EXEC=true` for its local sample-media loop — **production MUST NOT
set this variable**; the production Ring path uses plain `rtsp://` sources via ring-mqtt's
RTSP gateway and needs no `exec:`. Keep this flag unset on any host that ingests Ring
streams.

### Ring bridge selection (Phase 2 validated: 2026-09-09)

The validated bridge is **ring-mqtt** (`tsightler/ring-mqtt`, currently pinned `5.9.3` for
the Mac POC — re-pin at production deployment per constitution VI.3). It authenticates to
Ring cloud via a **refresh token** (2FA required; obtained interactively via the bundled
`init-ring-mqtt.js` CLI) and exposes each Ring camera as a **local on-demand RTSP gateway**
(`rtsp://<host>:8554/<camera_id>_live`, `<camera_id>` from device discovery, never
invented). Proven on the Phase 2 Mac POC: live Front Door stream (Ring Doorbell Pro 4,
H.264 720×720) ingested by Frigate, person detected, event delivered over MQTT — in
bounded test windows.

**Bounded-use constraint (NON-NEGOTIABLE for this project):** Ring cameras are
cloud/on-demand devices. ring-mqtt explicitly does **not** support continuous/24x7
streaming — while a Ring camera is actively streaming it stops sending motion/ding events,
and sustained streaming drains batteries and risks overheating. Production MUST use an
event-triggered workflow (start stream on motion/ding → bounded analysis window → stop).
The Phase 2 Mac POC established this pattern; production must not regress to always-on
Ring ingestion. Production MUST also enable `livestream_user`/`livestream_pass` RTSP
credentials (not needed for the loopback-only Mac test, but required before exposing RTSP
beyond a single host — constitution II.4).

---

## A. Raspberry Pi 3 — Home Assistant Production

### Existing role

The Pi 3 already runs Home Assistant OS and is the household's automation control plane
(constitution Principle I.1). This feature adds to what it already does — it does not
replace or restructure it. Everything the Pi already handles (Ring doorbell/motion
automations, media controls, thermostat logic, dashboards, other MQTT functions) continues
unchanged.

### Components running on the Pi

- **Home Assistant OS** (existing)
- **Mosquitto Broker** (existing, if already installed as the Pi's MQTT integration; if not
  yet installed, this is a standard Home Assistant add-on — installing it is Pi-appropriate
  and does **not** conflict with I.1/I.2, since Mosquitto itself is not an AI workload)
- **Home Assistant's Frigate integration** — the official integration that subscribes to
  Frigate's MQTT events and surfaces them as HA entities. This is the *only* new HA-side
  component this feature adds to the Pi.
- **Ring integration** (existing) — unchanged, independent of this feature (constitution
  III.3, IV.1)
- **Mobile notification service** (existing — `notify.mobile_app_pk_world`)

### Existing entities this feature must respect, not replace

Per constitution Article VIII.1, only these (already-verified) entities may be referenced —
no automation may be built from an assumed or invented entity ID:

- `event.front_door_ding`
- `event.front_door_motion`
- `switch.front_door_motion_detection`
- `notify.mobile_app_pk_world`
- `person.praveen_kumar_konathala`

This feature's notification automations (tasks.md T047–T050) are **new** automations that
read Frigate/MQTT data and call `notify.mobile_app_pk_world` — they do not modify the
existing Ring-driven automations built on `event.front_door_ding` /
`event.front_door_motion`.

### MQTT requirements

- The Pi's Home Assistant instance and the production Frigate host must be configured against
  the **same** MQTT broker (constitution VIII — event/config entities must not be confused;
  PD-08's mechanics-only Phase 1 check becomes this feature's actual Phase 4 requirement).
- Production MQTT **must** use authentication (constitution II.4) — unlike the Phase 1
  isolated dev broker documented in `local-mac-testing.md`, which deliberately has none.
- Document the production broker's host/port at deployment time in a gitignored
  `.env` (never in this file, never in git) — see `production-security` below.

### Network connectivity requirements

- The production AI host (B) must be able to reach the Pi's MQTT broker (or vice versa,
  depending on which host runs the broker) over the local network.
- The Pi does not need direct network access to Ring — Ring connectivity is handled by
  whichever host runs Ring-MQTT/the video bridge (typically the AI host, or a separate small
  always-on device, per Phase 2's design work — not yet finalized in this project).

### How HA consumes Frigate events

Same semantic contract as documented in
[`contracts/mqtt-events.md`](../../specs/001-front-door-person-identification/contracts/mqtt-events.md):
Home Assistant's Frigate integration subscribes to `frigate/events` (and `frigate/available`
for the AI-host-offline failure state) on the shared broker. The relationship-lookup and
notification-composition logic (tasks.md T043–T050) run entirely as Home Assistant
automations/Jinja2 templates on the Pi — no new service is introduced on either host for this
(constitution I.1, VI.1; research.md #5).

### Relationship mapping

**The deployment mechanism for the real relationship-mapping data is not yet decided and is
pending Phase 4 implementation.** Don't infer one from this document. What *is* decided — the
governing rules, independent of however the mechanism ends up working:

- Identity recognition (Frigate) determines only the enrolled identity name — nothing else.
- The relationship category (Family/Friend/Neighbor/Other Known) is manually maintained by
  the homeowner, never inferred from appearance (constitution III.2, FR-007).
- Home Assistant remains the household control/orchestration layer for this mapping — it is
  not delegated to Frigate or any other component (constitution I.1).
- No new external relationship database is introduced unless Phase 4 implementation actually
  proves the current approach (a homeowner-edited YAML file, schema:
  [`contracts/identity-library-schema.md`](../../specs/001-front-door-person-identification/contracts/identity-library-schema.md))
  is insufficient. Adding infrastructure ahead of that proof would violate constitution VI.1
  ("minimize the stack").
- Whatever the eventual deployment mechanism turns out to be, the real mapping file is never
  committed to git (constitution II.4). Document the chosen mechanism here once Phase 4
  actually decides it — not before.

### Notification automation

Implements FR-014–FR-016, FR-030 (tasks.md T047–T050): known-person notifications include
name + relationship category when configured; unknown-person notifications say so explicitly;
a 5-minute per-person dedup window prevents spam; multiple people in one event are merged into
a single notification.

### Failure isolation (constitution IV.1, NON-NEGOTIABLE)

**If the Frigate/AI host is offline:**
- Ring doorbell automation (`event.front_door_ding`) continues working, unaffected.
- Ring motion automation (`event.front_door_motion` /
  `switch.front_door_motion_detection`) continues working, unaffected.
- Home Assistant itself remains fully operational.
- Thermostat logic, media controls, dashboards, and all other automations remain operational.

**This must be true structurally, not just by accident** — the new Frigate-dependent
automations are additive (they call `notify.mobile_app_pk_world` on new triggers) and do not
sit in the dependency path of any existing automation. Task T053 is the acceptance test that
proves this against the real production instance before this feature is considered done.

**Do not run heavy AI workloads on the Raspberry Pi 3.** This is a hard constraint
(constitution I.1, I.2), not a performance suggestion — the Pi's entire value is being a
stable, low-power control plane that doesn't need AI compute to keep working.

---

## B. Production AI Compute Host

**Not yet selected.** This project has deliberately not committed to specific hardware —
constitution Principle I.2 requires the Phase 1 Mac proof-of-concept to establish real
CPU/GPU/storage/accuracy requirements *before* production hardware is chosen. The current
Intel Mac is the **development/POC host only** — it is not automatically promoted to
production; a separate, always-on host is expected (constitution: "Phase 5 – Production
host: move Frigate/AI to dedicated hardware").

### Minimum capabilities to validate before purchase/deployment

| Capability | Why it matters | How this project validates it |
|---|---|---|
| Supported CPU architecture | Frigate itself needs a standard x86_64 or ARM64 Linux-capable CPU | Confirmed via the same host-inventory approach as PD-01 |
| AVX/AVX2 instruction-set support | Required by Frigate's native face-recognition feature (this project's Phase 3 dependency) | PD-09 (task T031) — explicitly deferred until Phase 3, never assumed |
| RAM | Frigate + detector + (later) face recognition need headroom beyond a single camera's decode/detect load | Measured during Phase 1 (`docker stats` against the Mac POC) and re-measured on the actual candidate host before purchase |
| Storage | Clips/recordings/snapshots/face library, plus retention policy (constitution II.5) | Sized once Phase 1/3 establish real per-camera storage rates |
| Network | Must reach both the Ring video bridge and the Pi's MQTT broker reliably | Verified during Phase 2 rollout |
| Accelerator options (GPU/NPU) | Constitution IX.1/IX.2 — CPU-only detection works but is not recommended long-term; hardware acceleration reduces latency and power | Optional; evaluated against Phase 1's CPU-only baseline numbers |
| Docker support | The entire stack is containerized (constitution: "container-first") | Any modern Linux host with Docker Engine/Compose qualifies |
| Expected camera count | Constitution V.2 — Front Door only for the initial release; expansion (constitution Phase 6) needs proportionally more decode/detect headroom | Sized for 1 camera now; re-evaluated before Phase 6 |
| Decoding load | Directly proportional to camera count × resolution × fps | Measured per constitution IX.1 before adding cameras |
| Person detection | The Phase 1 baseline capability | Proven on the Mac; must be re-proven on the actual candidate host, not assumed to carry over |
| Face recognition | The Phase 3 capability | Explicitly gated on AVX2 (PD-09) — never assumed from CPU family alone |
| Future camera expansion headroom | Constitution VI's "additional cameras only after Phase 1 validation" | Purchase decision should leave margin, not size exactly to 1 camera |

**Do not select hardware permanently based on this document alone.** These are the criteria
to validate; the actual selection happens after Phase 1 (and ideally Phase 3, for the face
recognition requirement specifically) produce real numbers.

---

## Production Security

- **No biometric media in Git.** Enforced by `.gitignore` in this repo (see
  `CONTRIBUTING.md`'s pre-commit checklist); on the production host, face reference
  images/embeddings live in Frigate's own data volume, never in any git-tracked path
  (constitution II.4, research.md #6).
- **Secrets outside the repository.** MQTT credentials, Ring tokens, and any other production
  secret live in `.env`/Home Assistant secrets/Docker secrets — never in this repo, never in
  chat, never in a commit (constitution II.4).
- **MQTT authentication in production.** The Phase 1 dev broker's `allow_anonymous true` is
  explicitly acceptable *only* because it's isolated and local-only (see
  `mosquitto/config/mosquitto.conf`'s own warning comment) — production MQTT must require
  authentication.
- **No unnecessary public Internet exposure.** Frigate's UI, the MQTT broker, and Home
  Assistant should be reachable only on the local network (or via an already-existing, already
  -audited remote-access method you use for HA today) — this feature does not introduce any
  new public-facing surface.
- **Local-first processing.** Face embeddings, the face library, and identity/relationship
  mappings stay on local infrastructure; no cloud face-recognition dependency is introduced
  (constitution I.3).
- **Least privilege.** The AI host's Frigate instance needs network access to the camera/video
  bridge and the MQTT broker — nothing more. It does not need, and should not be given, access
  to Home Assistant's own secrets or admin interface.
- **Backups.** Back up the Pi's Home Assistant config (existing practice, unchanged) and,
  separately, the AI host's Frigate config + the gitignored relationship-mapping file. Face
  embeddings themselves are regenerable from reference photos — back up the *photos*, not
  necessarily Frigate's derived embedding data, if storage is a concern.
- **Update strategy.** Per constitution VI.3: pin and document application/image/model/config
  versions; test upgrades to Ring integration, Frigate, MQTT, video decoding, object
  detection, or face recognition before production adoption — never auto-update the AI host
  unattended.
- **Data retention — baseline policy (constitution II.5).** This is the baseline policy, not
  a final numeric retention window — specific numbers are a deployment-time decision (see
  below):
  - Default retention = minimum necessary. Do not retain biometric training media, face
    crops, snapshots, or test videos longer than required for enrollment, validation,
    troubleshooting, or an explicitly configured security use case.
  - Do not enable indefinite retention by default.
  - Do not place biometric media in Git.
  - Do not expose biometric media publicly.
  - Retention periods for production recordings/snapshots remain a deployment-time decision
    and **must be explicitly documented here before production go-live** — this document is
    intentionally incomplete on that specific number until then.
  - Unknown-person recognition must not automatically create a persistent biometric
    identity/profile — an `Unknown` result stays an event outcome, never a stored identity
    (constitution II.1, II.2).
- **Face recognition never directly grants physical access.** NON-NEGOTIABLE (constitution
  II.3, FR-025) — no door lock, garage door, or alarm-disarm automation may ever depend on a
  face-recognition result, in this phase or any future one without a formal constitution
  amendment.
- **`Unknown` remains the safe default.** NON-NEGOTIABLE (constitution II.2) — production
  confidence thresholds must favor precision over aggressive matching, same as documented in
  `research.md` #9 for the Phase 1/3 starting policy.

---

## Production Acceptance Sequence

Run in order; each step should pass before moving to the next. This is the production
equivalent of the Phase 1 local checklist in `local-mac-testing.md` §17 — do not skip steps
to save time (constitution V.1).

1. **Pi reachable** — network connectivity to the Raspberry Pi 3 confirmed.
2. **MQTT reachable** — both the Pi and the AI host can reach the shared, authenticated
   production broker.
3. **AI host reachable** — network connectivity to the production Frigate host confirmed.
4. **Frigate healthy** — starts cleanly, UI reachable, no restart loop (same criteria as PD-05,
   now against production config/hardware).
5. **Ring stream healthy** — the real Front Door RTSP stream (via Ring-MQTT/go2rtc) ingests
   reliably (constitution Phase 2 scope).
6. **Person detection works** — against the real, live stream, not a looped test clip.
7. **Known-person test works** — an enrolled identity is correctly recognized under normal
   conditions (spec SC-003).
8. **Unknown-person test works** — an unenrolled person is correctly reported as `Unknown`
   (spec SC-002).
9. **Relationship mapping works** — a recognized identity's configured category appears in
   the result (spec US3).
10. **iPhone notification works** — the real `notify.mobile_app_pk_world` delivers a
    known-person and an unknown-person notification within the SC-005/SC-006 15-second target.
11. **AI host shutdown test** — stop Frigate/the AI host entirely.
12. **Existing Ring notification still works** — with the AI host down, doorbell/motion
    notifications via `event.front_door_ding`/`event.front_door_motion` still fire normally
    (constitution IV.1, spec FR-018/SC-008 — this is task T053's real-HA acceptance test).
13. **Pi remains responsive** — the Pi's own UI, automations, and other integrations are
    unaffected by the AI host being down.
14. **Restart/recovery test** — bring the AI host back up; confirm Home Assistant resumes
    receiving enriched events without requiring the base security automations to be rebuilt
    (spec US5 Acceptance Scenario 3).
15. **Final rollback procedure** — confirm you can fully disable the Frigate HA integration
    (or stop the AI host indefinitely) and have the household's existing Ring automations
    continue working exactly as they did in Phase 0, with zero dependency on this feature ever
    having existed. Document the exact rollback steps here once production deployment happens.

---

## Document links

- [spec.md](../../specs/001-front-door-person-identification/spec.md)
- [plan.md](../../specs/001-front-door-person-identification/plan.md)
- [tasks.md](../../specs/001-front-door-person-identification/tasks.md)
- [validation-report.md](../../specs/001-front-door-person-identification/validation-report.md)
- [local-mac-testing.md](../testing/local-mac-testing.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)
- [constitution](../../.specify/memory/constitution.md)
