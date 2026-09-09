# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

Feature `001-front-door-person-identification` has a ratified spec, plan, and tasks.md, and has
**completed its Foundational gate (T019 = PASS)** plus **Constitution Phase 1 (T020–T026 =
PASS, person-detection MVP)** and **Constitution Phase 2 (T027–T030 = PASS, live Ring Front
Door stream proven in bounded tests)** — see
`specs/001-front-door-person-identification/validation-report.md` for the authoritative
pass/fail state. The Mac POC stack (`docker-compose.yml`: Mosquitto + Frigate + throwaway HA
+ ring-mqtt bridge) runs locally — see `docs/testing/local-mac-testing.md` for how to start
it and what to check.

**Ring streaming is bounded-use only.** Ring cameras are cloud/on-demand devices;
continuous streaming via ring-mqtt is unsupported (motion/ding loss, battery drain). The
Phase 2 live tests used short deliberate windows and the Frigate config was restored to the
looped sample-media source afterward (`docs/testing/local-mac-testing.md` §13a). Ring auth
(2FA refresh token) lives in gitignored `ring-mqtt/data/`.

**T031 (PD-09 face-recognition hardware gate) has been executed, and PD-09 is now
`PD09_PASS`.** The host hardware fully satisfies Frigate's documented AVX+AVX2 requirement
(raw `AVX1.0`/`AVX2` CPU flags verified; native x86_64 Docker). The first T031 check found
`PD09_FAIL_FRIGATE_BUILD` (the then-pinned 0.15.1 lacked the feature, which arrived in
0.16.0), and the user-approved controlled upgrade to **Frigate 0.17.2** (current stable)
resolved it: full `run_harness.sh all` regression passes unchanged, MQTT event contract
holds, and an isolated probe confirms `face_recognition` config with `model_size: small` is
accepted (FEATURE_PRESENT = YES). One 0.17 breaking change is handled locally: go2rtc
`exec:` sources are blocked by default, so the dev POC sets
`GO2RTC_ALLOW_ARBITRARY_EXEC=true` **for the local sample-media loop only** — production
(Phase 5) must use plain RTSP sources and must NOT set it.

**T032 (enable native face recognition, small model) has been executed and passed.**
`frigate/config/config.yml` now has a global `face_recognition:` block
(`enabled: true, model_size: small` — FaceNet, CPU-only; large/ArcFace stays
production-only), with the Frigate 0.17.2 conservative defaults written explicitly
(detection 0.7 / unknown 0.8 / recognition 0.9 — favor `Unknown`, constitution II.2; NOT
tuned). The subsystem initializes cleanly (embedding process, small-model files
downloaded), the full `run_harness.sh all` regression remains OVERALL PASS with face
recognition on, MQTT payloads keep `sub_label: null`, and the throwaway HA still receives
events. **No identities are enrolled** — the face library is empty.

**T033 (pre-enrollment face-processing validation) has been executed and passed (2026-09-09).**
With zero enrolled identities, T033 honestly validated the pre-enrollment surface and
deferred threshold tuning: `THRESHOLD_TUNING_STATUS = DEFERRED_UNTIL_ENROLLMENT` (T034+).
Verified: face subsystem active (`face_recognition_speed ~11.5ms` measured) but **zero
face classifications complete** (fps 0.0) and **zero biometric artifacts** (0 files in
`/media/frigate/clips/faces/`, no face DB tables) — code-verified that
`FaceNetRecognizer.classify` returns None with an empty embeddings map, so `write_face_attempt`
never runs pre-enrollment. Event semantics unchanged (`label=person`, `sub_label=null`, no
face MQTT topic, `/api/faces` → `{}`). Full regression OVERALL PASS — person detection is
independent of face processing (FR-002/FR-017). Baseline thresholds unchanged and NOT
claimed as tuned. **Privacy/retention finding for production**: once identities exist,
Frigate auto-saves every classified face attempt (incl. unknown faces) as `.webp` under
`/media/frigate/clips/faces/train/` up to `save_attempts` (default 200) — production must
plan retention/cleanup for unknown-face crops (constitution II.5; recorded in
validation-report.md and production-deployment.md). Next: T034 (enroll first Known
Identity), pending explicit approval.

This repo has no application source code yet — only configuration (Docker Compose,
Frigate, Mosquitto), scripts (`scripts/loop-test-video.sh`), and documentation. Identity/
relationship/notification logic, once implemented (T043+), will be Home Assistant
automations/Jinja2 templates, not custom application code (per the plan's Technical
Context).

## Local Test Documentation Gate

Every feature must have documented local validation steps, kept current, before it can be
committed as complete — see [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full rule and
pre-commit checklist. Feature-local testing docs live under `docs/testing/` and are linked
from the corresponding `specs/<feature>/` directory.

## Spec-kit workflow

This project uses [GitHub spec-kit](https://github.com/github/spec-kit) for spec-driven development,
configured for the Claude integration (`.specify/`, `.claude/skills/speckit-*`). Work should flow through
these skills in order, one feature at a time:

1. `/speckit-constitution` — establish/update project principles (`.specify/memory/constitution.md` is
   still the unfilled template — run this before the first real feature if project-wide principles matter).
2. `/speckit-specify` — turn a feature description into `spec.md` for a new feature branch/dir under `specs/`.
3. `/speckit-clarify` — resolve ambiguities in the spec before planning (run before `/speckit-plan` unless
   explicitly skipped).
4. `/speckit-plan` — generate design artifacts (`plan.md`, etc.) from the spec.
5. `/speckit-tasks` — generate a dependency-ordered `tasks.md` from the plan.
6. `/speckit-analyze` — cross-check spec/plan/tasks for consistency (non-destructive, read-only).
7. `/speckit-checklist` — optional, generates a domain-specific quality checklist.
8. `/speckit-implement` — execute `tasks.md` to actually write code.
9. `/speckit-converge` — after manual changes, reconcile the codebase against spec/plan and append any
   missed work back into `tasks.md`.

Each of these is a Claude Code skill (invoke via `/speckit-*`), not a raw script — read the corresponding
`.claude/skills/speckit-*/SKILL.md` if you need the exact procedure it follows.

## Project purpose and target architecture

The goal (full detail in `Home_Assistant_Ring_Face_Recognition_Requirements.pdf`) is to add local person
detection and face recognition to an existing Home Assistant setup, using the Ring Front Door camera:

```
Ring Front Door
  -> Ring cloud / Ring-MQTT bridge (RTSP via go2rtc)
  -> Frigate on a separate compute host (NOT the Raspberry Pi)
  -> person detection -> face recognition (Frigate's native sub-label feature)
  -> known name OR Unknown
  -> relationship mapping (Family / Friend / Neighbor / Other Known) — a manually maintained lookup,
     never inferred from appearance
  -> MQTT -> Home Assistant (on Raspberry Pi 3)
  -> iPhone notification / dashboard / future automation
```

Key hard constraints from the requirements doc — treat these as non-negotiable when designing or
implementing anything in this repo:

- **Home Assistant stays on the Raspberry Pi 3**; Frigate/face recognition must run on separate compute
  and must never be hosted on the Pi.
- **Fail-safe by default**: any uncertain/low-confidence match must resolve to `Unknown`, never a guessed
  identity. Home Assistant automations must keep working even if the AI host is offline.
- **Relationship category is manual metadata** (a name -> category mapping maintained by the user),
  never inferred from facial appearance.
- **Notification-only in this phase** — face recognition must not control locks, alarms, or other
  security-critical actuators.
- **Local-first**: face embeddings, the face library, and Ring/HA credentials stay on local
  infrastructure and are never committed to git or stored in plain text in the project.
- **Apple Silicon limitation**: Frigate's native face recognition requires x86 AVX/AVX2, which Apple
  Silicon Macs lack. An Apple Silicon Mac can validate streaming/MQTT/HA integration/person detection,
  but not native face recognition — only an Intel Mac (or the eventual production host) can do that.

## Implementation phases (from the requirements doc)

Work is expected to proceed in this order; check which phase is current before starting new work:

1. **Phase 0 – Baseline**: existing Ring ding/motion Home Assistant automations (already working).
2. **Phase 1 – Mac POC**: Docker + MQTT + Frigate + a test video source, validating person detection
   without a live Ring stream.
3. **Phase 2 – Ring stream**: add Ring-MQTT/go2rtc, prove live Front Door RTSP ingestion into Frigate.
4. **Phase 3 – Identity**: enable face recognition on supported (AVX/AVX2) hardware, build the face
   library.
5. **Phase 4 – HA intelligence**: identity -> relationship mapping and notifications in Home Assistant.
6. **Phase 5 – Production host**: move Frigate/AI to dedicated hardware (e.g. an Intel mini-PC with
   OpenVINO).
7. **Phase 6 – Expansion**: add other Ring cameras after Front Door accuracy is proven.

This repo is currently mid-Constitution-Phase-3: the person-detection MVP (Phase 3),
Ring-stream integration (Phase 4), and face-recognition enablement (T032, Phase 5) are
complete; no face library exists yet (empty library, no enrollment) and no Home Assistant
automation code exists here yet.
