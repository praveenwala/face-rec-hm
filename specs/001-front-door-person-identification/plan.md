# Implementation Plan: Front Door Person Identification

**Branch**: `001-front-door-person-identification` | **Date**: 2026-09-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-front-door-person-identification/spec.md`

## Summary

Detect a person at the Ring Front Door camera, attempt to match them against an
intentionally enrolled Identity Library, and surface a `Known`/`Unknown` result — with a
manually-maintained relationship category when known — as a Home Assistant mobile
notification, without ever touching physical-access control and without ever degrading the
existing Ring doorbell/motion automations.

This plan spans the full feature (detection → identity → relationship → notification), but
its execution is **phase-gated** per constitution Article V.1 and the Phase-Gated Delivery
principle: `/speckit-tasks` groups tasks by constitution phase (1→4), so only Phase 1 tasks
are actionable today. Later-phase tasks (Ring streaming, native face recognition, production
HA wiring) exist in the plan for continuity but stay blocked until their phase's
prerequisites are met, per the `/grill-me` session for this feature (2026-09-09).

Technical approach: no new application code. The entire pipeline is composed from existing
containerized services (Frigate, Mosquitto, go2rtc) orchestrated by Docker Compose, with all
identity-to-notification enrichment logic implemented as Home Assistant automations/templates
— consistent with constitution I.1 ("Home Assistant remains the control plane") and VI.1
("minimize the stack").

## Technical Context

**Language/Version**: No general-purpose application language. YAML for Docker Compose,
Frigate config, and Home Assistant configuration; Jinja2 for Home Assistant automation
templates; Bash for the automated test harness and go2rtc/ffmpeg test-source orchestration.

**Primary Dependencies**: Docker Desktop + Docker Compose; Frigate (person detection +
native face recognition, container); Mosquitto MQTT (container, isolated instance for Phase
1); go2rtc (test-video RTSP restreaming, Frigate-bundled or standalone container); Home
Assistant (throwaway container for Phase 1 integration validation; the real instance stays on
the Raspberry Pi 3 and is only wired in later, per the failure-isolation split decided in
`/grill-me`); Ring-MQTT (Phase 2+, not needed for Phase 1); ffmpeg/ffprobe;
`mosquitto_pub`/`mosquitto_sub` CLI for MQTT smoke testing.

**Storage**: Local filesystem only. Frigate's own data volume holds clips/snapshots/face
embeddings, mounted from **outside the git working tree** (never repo-relative — constitution
II.4). The name→relationship-category mapping is a local YAML file inside the repo,
gitignored, with a committed `.example` template. No database.

**Testing**: An automated Bash harness in `tests/` drives the looped go2rtc test-video source
and asserts on Frigate's MQTT output (person event fires; no false event on the no-person
clip) via `mosquitto_sub`. Real human walk-up tests (SC-001–SC-004 in their live form) stay
manual and are logged once a live camera/person is available (Phase 2+).

**Target Platform**: macOS (confirmed Intel — `i9-9980HK`, x86_64 — via `/grill-me`) for
Phase 1–3 development. Home Assistant itself never leaves the Raspberry Pi 3 in production
(constitution I.1/I.2). Production AI compute is a later, separately-selected host
(constitution Phase 5).

**Project Type**: Infrastructure/configuration project — a single containerized
home-automation pipeline, not a client/server application. No custom source code beyond
config, automations, and test scripts.

**Performance Goals**: Notification delivery within 15 seconds of the enriched event
reaching Home Assistant under normal local-network conditions (spec SC-005/SC-006).

**Constraints**: `Unknown` is always the safe default on low confidence (II.2); no
facial-recognition-only physical-access control, ever (II.3, FR-025); credentials and
biometric data never committed to git (II.4); existing Ring doorbell/motion automations must
keep working through any AI-subsystem failure (IV.1); native face recognition requires
x86 AVX/AVX2 — confirmed available on the current dev host, but this MUST still be
independently re-verified at PD-09 time, not assumed from the earlier CPU check alone.

**Scale/Scope**: Single household, one required camera (Front Door) for the initial release
(FR-023); a small Identity Library (on the order of household members/regular visitors); a
5-minute per-person notification cooldown (FR-016, decided in `/grill-me`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design below.*

| Principle | Status | Notes |
|---|---|---|
| I.1 — HA remains the control plane | **PASS** | Enrichment/dedup/relationship logic lives entirely in HA automations & Jinja templates (`/grill-me` decision) — no custom bridge service. Production Pi is untouched during Phase 1. |
| I.2 — AI workloads run separately | **PASS** | Frigate + Mosquitto run in Docker on the Mac; never on the Pi. |
| I.3 — Local processing preferred | **PASS** | No cloud face-recognition service; Ring's existing cloud dependency is unchanged and out of scope. |
| II.1 — Explicit enrollment only | **PASS** (Phase 3+ scope) | FR-003/FR-022; no code path auto-creates identities. Not exercised until Phase 3. |
| II.2 — Unknown is the safe default | **PASS** | FR-005/006/029; starting confidence threshold is deliberately conservative (`/grill-me`). |
| II.3 — No physical-access control | **PASS** | FR-025, SC-011; notification-only scope, unconditionally. |
| II.4 — Protect credentials/identity data | **PASS** | `.gitignore` already excludes `.env*`, `*secrets*`, and identity/face-library paths (committed in the initial commit); face data lives outside the repo entirely. |
| II.5 — Minimize retention | **DEFERRED to Phase 3** | No face data exists yet to retain; retention configuration is a Phase 3 (Identity) concern. |
| III.1 — Person detection comes first | **PASS** | Frigate person detection always precedes any recognition attempt (FR-001). |
| III.2 — Identity/relationship are separate | **PASS** | Frigate produces `recognized_name` only; the relationship-category lookup is a separate HA-side mapping (FR-008/FR-010). |
| III.3 — Preserve the original security event | **PASS** | FR-002/FR-017; the base person-detection event is never suppressed by identity-processing failure. |
| IV.1 — AI failure must not break HA | **PASS, staged verification** | Phase 1 proves the mechanics via a throwaway HA container; the full failure-isolation acceptance test (US5/FR-018/SC-008) against the *real* Pi-hosted HA is explicitly deferred to Phase 4 (`/grill-me` decision — a throwaway HA has no real automations to protect). |
| IV.2 — Every dependency needs a failure state | **PASS for Phase 1 scope** | `pre-development-validation.md` PD-01–PD-10 cover Docker/MQTT/Frigate/HA-container failure states. Ring-specific failure states (stream unavailable, auth failure) are Phase 2 scope, not yet applicable. |
| IV.3 — Don't treat unknown data as real data | **PASS** | FR-019; explicitly carried into data-model.md below. |

No unjustified violations. **Complexity Tracking is empty** — no gate failures to justify.

**Post-Phase-1 re-check**: `data-model.md`, `contracts/`, and `quickstart.md` were reviewed
against the table above after drafting. No new violations were introduced — the MQTT contract
still routes through Frigate/HA only (I.1, VI.1), the relationship-mapping schema stays
homeowner-authored and gitignored (II.4, III.2), and the quickstart's throwaway-HA step
matches the IV.1 staged-verification note. Gate remains **PASS**.

## Project Structure

### Documentation (this feature)

```text
specs/001-front-door-person-identification/
├── spec.md                       # Feature specification (clarified)
├── plan.md                       # This file
├── research.md                   # Phase 0 output
├── data-model.md                 # Phase 1 output
├── quickstart.md                 # Phase 1 output
├── contracts/                    # Phase 1 output
│   ├── mqtt-events.md
│   └── identity-library-schema.md
├── pre-development-validation.md # Pre-existing: PD-01–PD-10 gate (must pass before Phase 1 tasks run)
├── validation-report.md          # To be produced by the first Phase 1 task, once the gate passes
├── checklists/
│   └── requirements.md
└── tasks.md                      # Phase 2 output (/speckit-tasks — not created by this command)
```

### Source Code (repository root)

Adopting constitution Article X.1's recommended layout now, per the `/grill-me` decision to
build it as part of Phase 1 setup tasks rather than let it drift:

```text
face-recognition/
├── docker-compose.yml        # Frigate + Mosquitto (+ throwaway HA for Phase 1 PD-08 only)
├── .env.example
├── frigate/
│   └── config/
│       └── config.yml        # Minimal Phase 1 config: go2rtc test source, person detection only
├── ring-mqtt/                # Phase 2+: empty until Ring streaming begins
├── home-assistant/
│   ├── automations/          # Enrichment: dedup, multi-person merge, relationship lookup (Phase 4)
│   └── helpers/
│       └── relationship_mapping.yaml.example   # Committed template; real mapping is gitignored
├── scripts/
│   └── loop-test-video.sh    # go2rtc/ffmpeg loop of the sample doorbell-angle test video
├── tests/
│   └── phase1/
│       ├── test-media/       # Sample photos/videos per pre-development-validation.md §5
│       └── run_harness.sh    # Automated: drives the looped video, asserts on MQTT output
└── docs/
    └── architecture.md
```

**Structure Decision**: This is a single containerized pipeline, not a client/server app —
none of the template's Option 1/2/3 layouts apply as-is. The structure above follows
constitution X.1 directly. Only the Phase 1 subset (`docker-compose.yml`, `frigate/config/`,
`scripts/loop-test-video.sh`, `tests/phase1/`) is created by this feature's Phase 1 tasks;
`ring-mqtt/` and the `home-assistant/automations/` content are placeholders until their
constitution phase (2 and 4, respectively) is reached.

## Complexity Tracking

*Empty — no Constitution Check violations to justify.*
