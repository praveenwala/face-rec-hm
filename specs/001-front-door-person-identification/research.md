# Phase 0 Research: Front Door Person Identification

All items below were `NEEDS CLARIFICATION` candidates in the Technical Context. Each was
resolved interactively via two `/grill-me` sessions (2026-09-09) rather than by independent
research, since the answers are project-specific decisions (constrained by
`.specify/memory/constitution.md`) rather than external best-practice lookups. Each entry
below is annotated with the constitution principle(s) it satisfies.

## 1. Plan/task structure across constitution phases

- **Decision**: One `plan.md` for the whole feature; `/speckit-tasks` groups generated tasks
  by constitution phase (1→4) so execution naturally stops at whatever phase current
  infrastructure supports.
- **Rationale**: The spec's user stories span phases 1, 3, and 4, but the constitution's
  Phase-Gated Delivery principle (Article V.1) forbids starting later-phase work before the
  current phase's goals are met. Splitting into 4 separate spec-kit features was rejected as
  unnecessary fragmentation of one coherent feature.
- **Alternatives considered**: One plan ignoring phase boundaries (rejected — violates V.1);
  four separate spec-kit features, one per phase (rejected — fragments a single coherent
  feature and duplicates spec content).

## 2. Development host architecture

- **Decision**: Confirmed Intel (`i9-9980HK`, x86_64) via `sysctl -n
  machdep.cpu.brand_string` and `uname -m`.
- **Rationale**: Constitution V.3 requires verifying Mac architecture before relying on it;
  native Frigate face recognition needs x86 AVX/AVX2, which this host has.
- **Alternatives considered**: N/A — this is a fact-finding item, not a design choice. Result:
  native face recognition is achievable on this same host later (Phase 3), not just person
  detection.

## 3. Phase 1 test video source

- **Decision**: A looping sample doorbell-angle video, restreamed as RTSP via go2rtc/ffmpeg.
- **Rationale**: Matches the eventual Phase 2 transport (RTSP from go2rtc against the real
  Ring stream), minimizing the swap-over. Satisfies constitution V.1's "test video source"
  step without requiring a live Ring stream.
- **Alternatives considered**: Live Mac webcam (rejected — not representative of the Ring's
  framing/angle); Frigate's public demo RTSP stream (rejected — doesn't exercise the actual
  go2rtc-based transport this project will use in Phase 2).

## 4. Phase 1 MQTT broker hosting

- **Decision**: A fresh, isolated Mosquitto container on the Mac, not the Pi's existing
  broker.
- **Rationale**: Constitution I.1's rule against workloads that degrade Home Assistant
  reliability, applied conservatively — nothing touches production while the pipeline is
  unproven.
- **Alternatives considered**: Connect to the Pi's existing broker (rejected for Phase 1 —
  would make an unproven pipeline visible in the real HA instance immediately).

## 5. Notification enrichment logic placement

- **Decision**: Home Assistant automations + Jinja2 templates implement the 5-minute
  per-person dedup, multi-person merge, and relationship-category lookup. No custom bridge
  service.
- **Rationale**: Constitution I.1 ("HA remains the control plane") and VI.1 ("minimize the
  stack") both favor not introducing a new service.
- **Alternatives considered**: A custom bridge service subscribing to Frigate's MQTT events
  and republishing an enriched event (rejected — one more component to build, deploy, and
  monitor, with no offsetting requirement that HA automations/templates can't satisfy).

## 6. Identity Library storage

- **Decision**: Split storage — face reference images/embeddings live entirely outside the
  git working tree, in Frigate's own data volume/config directory on the host. The
  name→relationship-category mapping is a local YAML file inside the repo path, listed in
  `.gitignore`, with a committed `.example` template documenting its structure.
- **Rationale**: Constitution II.4/II.5 forbid committing face data or credentials; the
  relationship mapping is not biometric, so documenting its shape (without real household
  data) is safe and useful.
- **Alternatives considered**: Everything outside the repo, including the relationship
  mapping (rejected — loses the benefit of a documented, versioned schema for the one
  non-sensitive piece of the Identity Library).

## 7. Repository layout adoption timing

- **Decision**: Adopt constitution Article X.1's recommended structure now, as part of Phase
  1 setup tasks, rather than letting it drift.
- **Rationale**: Keeps the constitution and the actual repo in sync from the start.
- **Alternatives considered**: Defer directory creation to whenever `/speckit-tasks` first
  needs them (rejected — risks drift between the documented and actual structure in the
  interim).

## 8. Phase 1 test automation approach

- **Decision**: An automated Bash harness in `tests/` drives the go2rtc-looped sample video
  and asserts on Frigate's MQTT output (person event fires on the person clip; no false event
  on the no-person clip). Real walk-up tests with an actual human stay manual, logged
  separately once live-camera phases exist.
- **Rationale**: Everything that doesn't require a live human is repeatable and CI-friendly;
  satisfies constitution V.4/V.5 (reproducible tests, explicit acceptance criteria) for the
  Phase-1-relevant subset of spec success criteria (SC-001, SC-002, SC-004).
- **Alternatives considered**: Fully manual test log only (rejected — the looped video makes
  automation straightforward, so manual-only would under-use a repeatable test source).

## 9. Confidence policy starting mechanism

- **Decision**: Use Frigate's native face-recognition confidence/similarity score directly
  (no separate scoring service), starting at a deliberately conservative threshold that
  favors `Unknown`, to be tuned later using SC-002/SC-003 walk-up test results.
- **Rationale**: Constitution VI.2 prefers native Frigate capability over a separate service;
  constitution II.2 (NON-NEGOTIABLE) requires favoring precision over aggressive matching, so
  a conservative starting point is the only defensible default.
- **Alternatives considered**: Leaving the starting threshold fully unspecified until Phase 3
  begins (rejected — the plan's Technical Context should commit to a mechanism, even if the
  exact numeric threshold is tuned later).

## 10. PD-08 (Home Assistant integration validation) vs. the Phase 1 isolation decision

- **Decision**: Run a second, disposable Home Assistant container on the Mac, pointed at the
  isolated Mac-local Mosquitto broker, purely to prove Frigate→MQTT→HA integration mechanics.
  The production Pi-hosted HA instance is never touched during Phase 1.
- **Rationale**: `pre-development-validation.md`'s PD-08 requires proving HA can see Frigate
  data, but decision #4 above already committed to never touching production HA during an
  unproven Phase 1. A throwaway HA container resolves the conflict.
- **Alternatives considered**: Temporarily pointing the real production HA at the Mac's
  broker (rejected — contradicts the isolation decision); deferring PD-08 entirely to Phase 4
  (rejected — leaves the Frigate→HA integration mechanics unproven until much later than
  necessary).

## 11. Failure-isolation acceptance testing (User Story 5 / FR-018 / SC-008) vs. PD-08

- **Decision**: PD-08 in the pre-development gate is scoped down to "the throwaway HA can see
  Frigate/MQTT data" (mechanics only). The full failure-isolation proof — stopping the AI
  subsystem and confirming the *real* doorbell/motion automations on the Pi keep working —
  becomes a feature-acceptance test performed later, once the pipeline is trustworthy enough
  to connect to the real HA (naturally around Phase 4).
- **Rationale**: A blank throwaway HA container has no existing Ring automations to protect,
  so PD-08's 4th check ("existing Ring automations MUST continue to work") is literally
  untestable against it. Splitting the check by scope resolves this without touching
  production early.
- **Alternatives considered**: Testing against the real HA now, read-only (rejected — accepts
  a brief but earlier-than-necessary touch of production configuration than the isolation
  decision intended).

## 12. Validation report location (PD-10)

- **Decision**: `specs/001-front-door-person-identification/validation-report.md`.
- **Rationale**: Keeps everything about this feature's readiness gate (spec, checklist,
  pre-development validation plan, and its result) in one place, consistent with how
  `checklists/requirements.md` is already organized.
- **Alternatives considered**: `tests/` at repo root (rejected — treats a spec-level gate
  artifact as a generic test artifact); `docs/` at repo root (rejected — disconnects it from
  the feature it gates).

## 13. MQTT smoke-test tooling (PD-03)

- **Decision**: `mosquitto_pub` / `mosquitto_sub` CLI clients, bundled with Mosquitto itself.
- **Rationale**: No new dependency beyond the broker already being installed; scriptable into
  the automated test harness (decision #8); consistent with constitution VI.1 ("minimize the
  stack").
- **Alternatives considered**: A GUI MQTT client such as MQTT Explorer or MQTTX (rejected —
  extra install, not scriptable into the automated harness).

## Outcome

All Technical Context unknowns are resolved. No `NEEDS CLARIFICATION` markers remain.
Proceeding to Phase 1 design.
