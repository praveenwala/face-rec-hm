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
validation-report.md and production-deployment.md).

**T034 (enroll the first Known Identities) is COMPLETE (2026-09-15).** Two identities
(referred to here as Person_A / Person_B, per validation-report.md convention — real names
never appear in this file) were enrolled via the Feature 002 enrollment workflow +
Frigate's native face API, 6 reference photos each. `tasks.md` also shows T039–T042
(unique-name enforcement, reference refinement, identity removal, no-silent-identity-
creation) all `[x]` PASS 2026-09-15, each exercised on a throwaway Frigate identity —
Person_A/Person_B were re-verified unchanged (6/6) after every one of these tests.
**T035–T038 remain PENDING/deferred** (checkboxes unchecked in tasks.md): they require
sustained per-track Known-person recognition producing a stable event `sub_label`, which
has not yet been observed — per-attempt recognition has been seen as high as 0.98, but the
Phase 5 checkpoint is explicitly **NOT cleared**. Root cause is recorded as Frigate 0.17.2's
per-track weighted-average consistency behavior, not a threshold/config/reference defect.

**Identity-removal defect (found via T035 testing, fixed, regression-tested, and now also
live-tested):** removing a Frigate identity deletes its reference crops via the API but
does **not** remove that identity's already-saved attempt crops under `faces/train/`; on a
recognizer rebuild those leftover crops could reintroduce a deleted identity. Fixed in
`FrigateEnrollmentService.remove_identity` (identity-scoped, best-effort train-crop purge).
Regression-tested offline in
`enrollment-app/backend/app/tests/test_removal_train_cleanup.py`; documented in
`docs/frigate-identity-removal.md`. This is spec-001's own task **T041** ("Implement
identity removal"), `[x]` PASS 2026-09-15 — a **different thing** from the "T041 bounded
live regression" label used in a later session (2026-09-16/17) for an ad-hoc live-system
validation exercise (create a throwaway identity + train residue against the real running
enrollment-backend/Frigate stack, remove it, force a recognizer rebuild, confirm no
reappearance) that PASSED against the deployed stack with Person_A/Person_B re-verified
6/6 throughout. That session also found the enrollment gate left ON via a stale/uncleaned
`docker-compose.t041-gate.override.yml` from that test; the gate has since been restored to
its documented default (OFF) and the override file deleted.

**Feature `002-known-person-enrollment-manager` (approved 2026-09-10):** a localhost-only
web application (`enrollment-app/` — FastAPI + SQLite backend, React/Vite frontend, native
Mac venv; NEVER the Pi) is the management surface for the known-person library: create
people with user-supplied relationships, upload/validate/approve enrollment photos
(Frigate-aligned YuNet quality checks, Phase 4), and an enrollment-readiness gate
(>= 5 distinct approved suitable photos, Phase 5). Phases 1–4 are complete, committed and
pushed (checkpoints `9a02e07` = Phase 3, `16eb3f2` = Phase 4), and **Phase 5 (Approval +
Readiness, T029–T033) is complete and validated (G5 = PASS) but NOT committed** (pending
user review) — see `specs/002-known-person-enrollment-manager/validation-report.md`.
Live: people CRUD and grouping, private multi-file photo upload (allowlist exactly
JPEG/PNG/WEBP by content sniffing, never extension; HEIC/GIF/BMP/TIFF →
`UNSUPPORTED_FORMAT`), automatic per-photo quality analysis (Frigate-aligned YuNet
`facedet.onnx` in the app-owned gitignored cache, `scripts/fetch_models.sh`; face count /
size ratio / sharpness / brightness → SUITABLE/UNSUITABLE/REVIEW_REQUIRED with explicit
reasons; **no silent Haar fallback** — missing model → `FACE_DETECTOR_UNAVAILABLE`, uploads
stay PENDING with an explicit `analysis_error`, re-analysis 503), explicit re-analysis
endpoint + UI, thumbnail/file serving, photo delete, audit log. **Phase 5: explicit photo
approval** (only `SUITABLE` may be approved — else `409 PHOTO_NOT_APPROVABLE`; idempotent
approve/unapprove; reanalysis that degrades an approved photo auto-clears approval,
detector failure during reanalysis preserves the prior result), **readiness**
(`GET /api/people/{id}/readiness`: `approved_suitable_count` ≥ 5 with each exact-duplicate
SHA-256 group counted once → `READY`, else `NOT_READY`; `READINESS_CHANGED` audited only on
effective transitions), **exact-duplicate protection** (same photo ×5 can never reach
READY), **advisory near-duplicate metadata** (pHash, Hamming ≤ 8 →
`near_duplicate_advisory` on a photo that stays `SUITABLE` — never `REVIEW_REQUIRED`
solely for similarity, never blocks approval, never deletes; both may be approved and
count), and a readiness UI
("N / 5 approved suitable photos — NOT READY / READY FOR ENROLLMENT"; READY is never
ENROLLED — no Frigate call, embedding, or identity creation is triggered by readiness).
**Phase 6 (Frigate enrollment) is now LIVE code, gated OFF by default** — this superseded
the earlier "blocked" state. `enrollment-app/backend/app/api/enrollment.py` owns three real
routes (`GET /api/frigate/status`, `POST /api/people/{id}/enroll`,
`DELETE /api/people/{id}/enrollment`) that call the real Frigate face API through
`FrigateEnrollmentService`; the old `501` stubs in `future.py` are retired. The single gate
is the `FRIGATE_ENROLLMENT_ENABLED` env var (`config.py`, default **False** — "Do NOT flip
this default without explicit authorization"). While OFF, every mutating call refuses
up-front with `FeatureNotEnabledError` (501 `FEATURE_NOT_ENABLED`) and performs zero
Frigate mutation — this is what the UI's disabled-control copy still describes. While ON,
it performs real enrollment/removal; the intended steady state is OFF, turned ON only for
short, explicitly authorized, bounded windows (T034, T039–T042, and the T041 live
regression all followed this pattern) and restored to OFF afterward. Feature 001's T034 is
COMPLETE (see above) — it used exactly this path, not just this app's readiness gate.
All biometric data lives under `enrollment-app/data/` (gitignored). Run: `enrollment-app/backend/run.sh`
(127.0.0.1:8000) + `cd enrollment-app/frontend && npm run dev` (127.0.0.1:5173); tests:
`enrollment-app/backend` venv → `python -m pytest app/tests` (115 tests; detection tests
need the model fetched via `scripts/fetch_models.sh`).

Except for that enrollment app, this repo has no other *deployed* application source code —
only configuration (Docker Compose, Frigate, Mosquitto), scripts
(`scripts/loop-test-video.sh`), and documentation for the Feature 001 POC stack.

**Phase 7 (HA intelligence) status — corrected; NOT "not implemented":** substantial
identity-normalization and production-prep work exists in `home-assistant/`, all committed
(`c205d80`, `549f19c`, `3c0940f`, `443d71f`, `4761693`, `875081c`), but **nothing has been
deployed to production Home Assistant** (`docs/production/gate-a-results.md`:
`LIVE_HA_UNCHANGED = YES`, `SAFE_TO_BEGIN_LIVE_IMPLEMENTATION = NO`):
- Identity/relationship normalization logic (frigate/events → known/unknown + relationship)
  is implemented as HA-native Jinja (`home-assistant/tests/c2_2/custom_templates/
  identity_normalization.jinja`), validated in four isolated stages against a Python
  reference oracle: C2.1 (oracle), C2.2 (real-HA-Template-engine render, 20/20 synthetic
  cases), C2.3 (automated parity proof, 42/42 passed against the oracle), C2.4 (full real-HA
  `check_config` validation of the isolated fixture). None of this touches any live/dev/
  production HA instance — self-contained, gitignored throwaway HA venv only.
  Identity/relationship logic is Jinja2 templates, not custom application code, matching
  the plan's Technical Context.
- A production-ready automation fragment (`home-assistant/automations/
  frigate_person_end_normalization.yaml`) and a helper include
  (`home-assistant/helpers/frigate_event_integration_helpers.yaml`) are committed and meant
  to be appended to production `automations.yaml`/`configuration.yaml`, but have **not**
  been appended yet. It only normalizes identity and fires an internal
  `frigate_person_normalized` HA event — it does **not** yet send any notification; the
  actual notification action is not implemented anywhere yet. It also depends on
  `helpers/relationship_mapping.generated.yaml`, which does not exist yet (only a schema
  example, `relationship_mapping.yaml.example`, is tracked); production has **no**
  relationship-mapping include (`gate-a-results.md`: "no existing relationship-mapping
  include observed").
- Real production infrastructure changes **have** been made (operator-executed, documented
  in `docs/production/mqtt-state-reconciliation.md`): the Mosquitto broker add-on was
  installed and the HA MQTT integration configured and verified online on the production
  Pi; a full HA backup was taken and verified, and its encryption key was rotated after an
  accidental exposure (remediated and verified). Frigate itself is still **not** connected
  to the production broker (`FRIGATE_MQTT_CONNECTED_TO_PRODUCTION = NO` as of that
  document). Locally, `docker-compose.yml`/`frigate/config/config.yml` currently have an
  **uncommitted** change (MQTT-B5) pointing the dev Frigate at the production broker
  (credentials via gitignored `.env`); as of this check the dev Frigate container shows
  that config loaded but no confirmed successful production MQTT connection in its logs —
  treat production MQTT transport as still unverified end-to-end, not working.
- No Ring/security automations were touched by any of this — verified independent
  (`gate-a-results.md`: `RING_SECURITY_PATH_DEPENDENT_ON_AI = NO`).

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
