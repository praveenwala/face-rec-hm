---
description: "Task list for Front Door Person Identification"
---

# Tasks: Front Door Person Identification

**Input**: Design documents from `/specs/001-front-door-person-identification/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md,
pre-development-validation.md — all present.

**Tests**: Included. `/grill-me` explicitly decided on an automated Bash test harness for the
Phase-1-automatable success criteria (research.md #8), so tests are in scope, not the
template's default "optional."

**Organization — deviation from the default template**: Tasks are grouped by **constitution
phase** (1→4), not by spec user-story priority (P1/P2/P3) alone. This is a deliberate decision
from `/grill-me` and `plan.md`'s Summary: the spec's user stories span constitution phases 1,
3, and 4 non-monotonically (US1/US5 → Phase 1; US2/US6 → Phase 3; US3/US4/US5-full → Phase 4),
so gating strictly by priority would violate the constitution's Phase-Gated Delivery
principle (Article V.1). Every task still carries its `[Story]` label for spec traceability.
**Only Phase 3 below (Constitution Phase 1) is actionable today.** Later phases are included
for continuity and are marked ⛔ **BLOCKED** until their prerequisites are met — do not start
them early.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US6, from spec.md. Omitted for Setup/Foundational/Polish tasks and for
  Constitution-Phase-2 tasks that have no single owning user story (Ring streaming is
  infrastructure shared by later stories, not its own story).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the constitution's recommended repo structure and Phase 1 configuration
scaffolding (plan.md's Project Structure).

- [x] T001 Create `frigate/config/`, `ring-mqtt/`, `home-assistant/automations/`,
  `home-assistant/helpers/`, `scripts/`, `tests/phase1/test-media/`, `docs/` directories per
  `plan.md`'s Project Structure
- [x] T002 [P] Create `.env.example` at repo root documenting required environment variables
  (MQTT host/port, Frigate config path) per `pre-development-validation.md` §7
- [x] T003 [P] Write `docker-compose.yml` defining `mosquitto`, `frigate`, and
  `ha-throwaway` services (research.md #4, #10; `plan.md` Technical Context)
- [x] T004 [P] Write `frigate/config/config.yml`: go2rtc-sourced test camera, person
  detection only (no face recognition yet), MQTT connection to the isolated broker
  (`contracts/mqtt-events.md`)
- [x] T005 [P] Write `scripts/loop-test-video.sh` to loop a sample doorbell-angle video
  through go2rtc/ffmpeg as an RTSP source (research.md #3)
- [x] T006 [P] Write `home-assistant/helpers/relationship_mapping.yaml.example` per
  `contracts/identity-library-schema.md`
- [x] T007 [P] Update `.gitignore` to explicitly exclude
  `home-assistant/helpers/relationship_mapping.yaml` (the real file) while still allowing
  `relationship_mapping.yaml.example` — the current `.gitignore` only has generic
  `*secrets*`/`identity-library/` patterns, not this specific path (constitution II.4)
- [ ] T008 **BLOCKED — awaiting user-provided sample media.** Collect and place sample test
  media under `tests/phase1/test-media/` per `pre-development-validation.md` §5 (5-10
  enrollment photos of one person; 3-5 short videos: known-person walk, unknown-person walk,
  no-person motion, low-light, optional two-person)

---

## Phase 2: Foundational — Pre-Development Validation Gate (Blocking Prerequisites)

**Purpose**: Execute `pre-development-validation.md` PD-01–PD-08. **⚠️ CRITICAL: No Phase 3
(or later) task may start until T019 passes** (constitution XI.1, PD-10).

- [x] T009 Execute PD-01 Host Capability Inventory; record in
  `specs/001-front-door-person-identification/validation-report.md` (Mac model, macOS
  version, RAM, disk, Docker version/arch — CPU architecture is already confirmed: Intel
  `i9-9980HK`, x86_64, via `/grill-me`) — **PASS**, disk free (16GB) and production-HA TCP
  reachability noted as non-blocking observations
- [x] T010 [P] Execute PD-02 Required Local Runtime check (Docker Desktop, Compose, Git,
  curl, VLC/ffplay, ffprobe, `mosquitto_pub`/`mosquitto_sub`); record in
  `validation-report.md` — **PASS** (ffmpeg + mosquitto-clients installed via Homebrew
  during execution)
- [x] T011 Execute PD-03 MQTT Validation: `mosquitto_pub`/`mosquitto_sub` round-trip test
  against the `docker-compose.yml` `mosquitto` service; record in `validation-report.md`
  (depends on: T003, T010) — **PASS**
- [x] T012 Execute PD-04 Container Validation: `docker compose up`/`down` smoke test, mount
  check; record in `validation-report.md` (depends on: T003) — **PASS**
- [x] T013 Execute PD-05 Frigate Baseline Validation: start Frigate with the minimal config,
  confirm UI reachable, no restart loop, no unresolved config errors; record in
  `validation-report.md` (depends on: T004, T012) — **PASS** after fixing 3 real bugs found
  during execution (port 5000 conflict, `/media` mount collision, go2rtc `exec:` producer
  syntax); ingestion mechanics proven via a synthetic non-biometric clip; real-clip run still
  needs T008
- [ ] T014 **BLOCKED on T008.** Execute PD-06 Media Validation: probe/decode every file under
  `tests/phase1/test-media/` with ffprobe per `pre-development-validation.md` §6; record
  results in `validation-report.md` (depends on: T008)
- [ ] T015 **PARTIAL — mechanism proven, real clip blocked on T008.** Run
  `scripts/loop-test-video.sh` and confirm Frigate ingests the RTSP source (depends on: T005,
  T013, T014)
- [ ] T016 **BLOCKED on T008/T015.** Execute PD-07 Person Detection Validation: feed the
  known-person and no-person clips, confirm `frigate/events` fires correctly for the former
  and not for the latter (depends on: T015)
- [x] T017 Stand up the throwaway Home Assistant container from `docker-compose.yml`; confirm
  it is reachable and is a separate instance from the production Pi-hosted HA (research.md
  #10) (depends on: T003) — **PASS**
- [ ] T018 **PARTIAL — broker/instance mechanics proven; event-visibility check blocked on
  T016.** Execute PD-08 in its mechanics-only scope (research.md #11): confirm the throwaway
  HA sees at least one Frigate-generated event/entity — this does **not** attempt the
  "existing Ring automations unaffected" check, which is deferred to T053 (depends on: T016,
  T017)
- [ ] T019 **FAIL (incomplete) — see validation-report.md.** Finalize `validation-report.md`
  with PASS/FAIL for PD-01–PD-08 and an explicit PD-09 (face-recognition hardware) deferral
  note (pre-development-validation.md PD-10) — the report is written and the gate result is
  recorded, but the gate itself does not pass until T008/T014/T016/T018 clear —
  **GATE: this must PASS before any Phase 3 task starts**

**Checkpoint**: Pre-development validation gate passes. Only now may Constitution Phase 1
implementation (below) begin.

---

## Phase 3: Constitution Phase 1 — Mac POC: Person Detection (User Story 1 + User Story 5 mechanics) 🎯 MVP

**✅ ACTIONABLE NOW once Phase 2's T019 passes.**

**Goal**: A person at the Front Door produces a person-detection event and a safe `Unknown`
identity result even with no face data; the base event survives identity-subsystem
unavailability (spec US1). The throwaway-HA mechanics proven in Phase 2 are now exercised as
this story's own acceptance test.

**Independent Test**: spec.md US1's Independent Test — an unenrolled person approaches the
Front Door; the system reports a person event and `Unknown` without any known-face data.

### Tests for User Story 1

- [ ] T020 [P] [US1] Add a `tests/phase1/run_harness.sh` assertion: the known/unknown-person
  clip produces a `frigate/events` message with `label: person` within a few seconds (spec
  SC-001)
- [ ] T021 [P] [US1] Add a `tests/phase1/run_harness.sh` assertion: the no-person/ordinary-
  motion clip produces no person-detection event (US1 Acceptance Scenario 3)
- [ ] T022 [P] [US1] Add a `tests/phase1/run_harness.sh` assertion: with identity processing
  (Frigate) stopped, the base person-detection event is still reported by whatever upstream
  signal is available (US1 Acceptance Scenario 4)

### Implementation for User Story 1

- [ ] T023 [US1] Confirm `frigate/config/config.yml` enables person detection only — no face
  recognition — for this phase (FR-001, FR-002) (depends on: T004)
- [ ] T024 [US1] Configure Frigate's MQTT publish settings so `frigate/events` matches
  `contracts/mqtt-events.md`'s semantic shape (depends on: T023)
- [ ] T025 [US1] Run `tests/phase1/run_harness.sh` against the looped test video; confirm all
  three assertions (T020–T022) pass; record the pass/fail summary (depends on: T020, T021,
  T022, T024)
- [ ] T026 [US5] Confirm, via the throwaway HA instance, that stopping the Frigate container
  does not disrupt the throwaway HA's own base operation — the mechanics-only failure-
  isolation check (research.md #11). **Note**: this does not satisfy the full US5 acceptance
  criteria (FR-018/SC-008), which require the real production HA and are deferred to T053.

**Checkpoint**: User Story 1 is fully functional and independently testable; this is the
feature's Phase 1 MVP scope.

---

## Phase 4: Constitution Phase 2 — Ring Stream

**⛔ BLOCKED** until the Phase 3 checkpoint passes and a Ring-MQTT-compatible bridge +
credentials are available. No dedicated user story owns this phase — it is shared
infrastructure enabling later stories.

- [ ] T027 [P] Select and configure Ring-MQTT (or another proven Ring video bridge) per
  constitution VI.2 (depends on: Phase 3 checkpoint)
- [ ] T028 Replace the looped test video source with the live Front Door RTSP stream via
  go2rtc; keep `scripts/loop-test-video.sh` for regression use (depends on: T027)
- [ ] T029 Re-run the `tests/phase1/run_harness.sh` assertions against the live stream;
  confirm person detection still functions on real footage (FR-023) (depends on: T028)
- [ ] T030 Update `validation-report.md` with live-stream validation results

**Checkpoint**: The live Ring Front Door stream reaches Frigate reliably; person detection
functions on real footage.

---

## Phase 5: Constitution Phase 3 — Identity (User Story 2 + User Story 6)

**⛔ BLOCKED** until the Phase 4 checkpoint passes and PD-09 (face-recognition hardware gate)
passes.

**Goal**: Enrolled people are correctly recognized with `Unknown` as the safe default; the
Identity Library can be managed without silent auto-enrollment (spec US2, US6).

**Independent Test**: spec.md US2's and US6's Independent Tests.

- [ ] T031 Execute PD-09: verify the pinned Frigate version's documented face-recognition
  requirements against the confirmed Intel host; record result in `validation-report.md`
- [ ] T032 [P] [US2] Enable Frigate's native face-recognition feature in
  `frigate/config/config.yml` (research.md #9; constitution VI.2) (depends on: T031)
- [ ] T033 [P] [US2] Set the starting confidence threshold conservatively, favoring `Unknown`
  (research.md #9; FR-005, FR-006) (depends on: T032)
- [ ] T034 [US6] Enroll the first Known Identity from the approved reference photos (stored
  outside the repo per research.md #6) (FR-003)
- [ ] T035 [US2] Test: the enrolled person's clip produces `frigate/events` with `sub_label`
  matching the enrolled name at/above the confidence policy (US2 Acceptance Scenario 1;
  SC-003) (depends on: T033, T034)
- [ ] T036 [US2] Test: a weak/partial/dark/blurred face resolves to `Unknown`, not a forced
  match (US2 Acceptance Scenario 2; SC-004) (depends on: T035)
- [ ] T037 [US2] Test: an unenrolled person resembling an enrolled person is not assigned
  that identity (US2 Acceptance Scenario 3) (depends on: T035)
- [ ] T038 [US2] Test: a printed photo/on-screen image of the enrolled person resolves to
  `Unknown`, not `Known` (FR-029; SC-013) (depends on: T035)
- [ ] T039 [US2] Enforce unique identity names at enrollment time; test that a duplicate-name
  enrollment is rejected or requires disambiguation (FR-031) (depends on: T034)
- [ ] T040 [US6] Implement identity refinement: update an enrolled identity's reference
  images; confirm future events use the updated set (FR-027; US6 Acceptance Scenario 2)
- [ ] T041 [US6] Implement identity removal; confirm the removed identity is never reported
  again (FR-021; US6 Acceptance Scenario 3)
- [ ] T042 [US6] Confirm a brand-new, never-enrolled face never silently creates a named
  identity (FR-022; US6 Acceptance Scenario 4)

**Checkpoint**: Enrolled identities are correctly recognized; unknowns and spoofing attempts
are correctly rejected; the Identity Library can be safely managed.

---

## Phase 6: Constitution Phase 4 — HA Intelligence (User Story 3 + User Story 4 + User Story 5 full)

**⛔ BLOCKED** until the Phase 5 checkpoint passes.

**Goal**: Recognized identities carry relationship context, notifications are useful and
rate-limited, and failure isolation is proven against the **real** production Home Assistant
(spec US3, US4, US5).

- [ ] T043 [P] [US3] Implement the relationship-category lookup as a Home Assistant
  automation/template reading `home-assistant/helpers/relationship_mapping.yaml` (research.md
  #5; `contracts/identity-library-schema.md`; FR-008–FR-010)
- [ ] T044 [US3] Test: a recognized identity with an assigned category returns both name and
  category (US3 Acceptance Scenario 1) (depends on: T043)
- [ ] T045 [US3] Test: a recognized identity with no assigned category is reported without an
  invented category (US3 Acceptance Scenario 2) (depends on: T043)
- [ ] T046 [US3] Test: an unrecognized person never has a relationship inferred (US3
  Acceptance Scenario 3; FR-007) (depends on: T043)
- [ ] T047 [P] [US4] Implement the known-person notification: includes name + category when
  configured (FR-014; US4 Acceptance Scenario 1) (depends on: T043)
- [ ] T048 [P] [US4] Implement the unknown-person notification wording (FR-015; US4
  Acceptance Scenario 2)
- [ ] T049 [US4] Implement the 5-minute per-person dedup/cooldown automation (FR-016; SC-007;
  first `/grill-me` session) (depends on: T047, T048)
- [ ] T050 [US4] Implement the multi-person merge: one notification listing every identified
  person from a single event (FR-030; SC-014) (depends on: T049)
- [ ] T051 [US4] Test: with the identity subsystem unavailable, a generic person-detected
  notification is still delivered (US4 Acceptance Scenario 4) (depends on: T026)
- [ ] T052 Wire the real production Home Assistant (Raspberry Pi 3) to the now-trusted
  MQTT/Frigate pipeline, replacing the throwaway HA instance used through Phase 5
  (constitution I.1/I.2; research.md #11)
- [ ] T053 [US5] Execute the full failure-isolation acceptance test against the **real**
  production HA: stop the AI subsystem, confirm existing Ring doorbell/motion automations
  remain unaffected (FR-018; SC-008 — deferred from Phase 3 per research.md #11) (depends on:
  T052)
- [ ] T054 [US5] Confirm the identification subsystem resuming afterward does not require
  rebuilding the base security automations (US5 Acceptance Scenario 3) (depends on: T053)
- [ ] T055 Measure end-to-end notification delivery latency; confirm the 15-second target
  (SC-005, SC-006) (depends on: T050, T052)

**Checkpoint**: All 6 user stories are functional against the real production Home Assistant
instance; the feature meets the constitution's Definition of Done.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T056 [P] Write `docs/architecture.md` documenting the final pipeline (constitution
  X.1)
- [ ] T057 [P] Document pinned dependency versions (Frigate, Mosquitto, go2rtc, Home
  Assistant) per constitution VI.3
- [ ] T058 Re-run `quickstart.md` end-to-end as a final regression check
- [ ] T059 [P] Confirm SC-012: for every reported identity result, the homeowner can trace
  which camera event produced it and its status (Known/Unknown/Unavailable/Failed)
- [ ] T060 Review the constitution's Definition of Done checklist and confirm every item is
  satisfied

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — **BLOCKS Phase 3 and everything
  after it** (T019 is the hard gate).
- **Constitution Phase 1 (Phase 3, US1+US5-mechanics)**: Depends on Phase 2's T019. **This is
  the only phase actionable today.**
- **Constitution Phase 2 (Phase 4, Ring Stream)**: Depends on Phase 3's checkpoint AND
  external Ring-MQTT credentials/hardware being available.
- **Constitution Phase 3 (Phase 5, US2+US6)**: Depends on Phase 4's checkpoint AND PD-09
  passing.
- **Constitution Phase 4 (Phase 6, US3+US4+US5-full)**: Depends on Phase 5's checkpoint.
- **Polish (Phase 7)**: Depends on Phase 6 (or whichever phase you stop at).

### User Story Dependencies

- **US1 (P1)**: Constitution Phase 1. No dependency on other stories.
- **US5 (P1)**: Split — mechanics slice in Phase 1 (T026), full acceptance test in Phase 4
  (T053–T054), per research.md #11.
- **US2 (P1)**: Constitution Phase 3 — despite its P1 spec priority, it cannot start until
  Phase 3's prerequisites (live-ish pipeline + face-recognition hardware gate) are met. This
  is the clearest example of why phase-gating overrides spec priority for scheduling.
- **US6 (P3)**: Constitution Phase 3, alongside US2 (identity management needs identity
  recognition to exist first).
- **US3 (P2)**: Constitution Phase 4 — depends on US2 existing (relationship context enriches
  a recognized identity).
- **US4 (P2)**: Constitution Phase 4 — depends on US3 (categories) and the Phase 1 mechanics
  (base notification path).

### Within Each Phase

- Tests are written alongside/just before the implementation task they validate (not a strict
  red-green-refactor gate, since most "tests" here are integration assertions against a real
  Frigate/MQTT pipeline, not unit tests of new code).
- Config/infrastructure before automations.
- Story complete (checkpoint) before moving to the next constitution phase.

### Parallel Opportunities

- All Setup tasks marked [P] (T002–T007) can run in parallel once T001 creates the
  directories.
- T010 (runtime check) can run parallel to T009 (host inventory).
- Within Phase 3, T020–T022 (test assertions) can be written in parallel.
- Within Phase 5, T032/T033 (Frigate face-rec config) can run parallel to nothing else until
  T034 (enrollment) — they're on the same file, mostly sequential in practice despite the [P]
  marker reflecting "different concerns."
- Within Phase 6, T043 (relationship lookup), T047, and T048 (notification wording) touch
  different automation files and can run in parallel.

---

## Parallel Example: Phase 1 Setup

```bash
# After T001 creates the directory structure, launch together:
Task: "Write docker-compose.yml defining mosquitto, frigate, and ha-throwaway services"
Task: "Write frigate/config/config.yml with a minimal person-detection-only config"
Task: "Write scripts/loop-test-video.sh"
Task: "Write home-assistant/helpers/relationship_mapping.yaml.example"
Task: "Update .gitignore for the real relationship_mapping.yaml"
```

---

## Implementation Strategy

### MVP First (Constitution Phase 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (pre-development validation gate — **T019 is a hard stop**)
3. Complete Phase 3: Constitution Phase 1 (US1 + US5-mechanics)
4. **STOP and VALIDATE**: run `quickstart.md` end-to-end; confirm US1's Independent Test
5. This is the feature's MVP — do not proceed to Phase 4 without new Ring-MQTT
   hardware/credentials and an explicit decision to continue

### Incremental Delivery (once unblocked)

1. Setup + Foundational → gate passes
2. Constitution Phase 1 → MVP: person detection working, safely defaulting to Unknown
3. Constitution Phase 2 → live Ring stream proven
4. Constitution Phase 3 → real identity recognition, safely rejecting unknowns/spoofs
5. Constitution Phase 4 → relationship-aware, rate-limited notifications against real HA;
   full failure-isolation proof
6. Polish

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks.
- [Story] label maps a task to its spec.md user story for traceability; omitted for
  Setup/Foundational/Polish and for the Ring-streaming phase (no single owning story).
- Phase gates (T019, and the checkpoint at the end of each constitution-phase section) are
  hard stops per constitution Article V.1 ("Build Incrementally") — do not skip ahead even if
  a later phase's tasks look easy to start early.
- Commit after each task or logical group.
- `validation-report.md` is a living document — update it, don't recreate it, as each PD
  check and later phase completes.
