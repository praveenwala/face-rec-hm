# Implementation Plan: Known Person Enrollment Manager

**Branch**: `002-known-person-enrollment-manager` | **Date**: 2026-09-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-known-person-enrollment-manager/spec.md`

## Summary

Build a localhost-only web application that becomes the management surface for the
known-person library: create people with a manually assigned relationship, upload and validate
enrollment photos against objective quality checks (the concepts behind feature 001's T034
media gate), compute enrollment readiness (>= 5 suitable approved photos), and — only in a
later, explicitly approved phase — enroll approved photos into Frigate 0.17.2's native face
library. Identity and relationship stay separate concepts: Frigate answers "who?", the app
holds "relationship = user-supplied metadata". Nothing here touches feature 001's
person-detection config, MQTT wiring, or Ring/HA automations; T034 stays NOT STARTED and the
`ENROLLMENT_MEDIA_NEEDS_MORE_PHOTOS` gate stays in force until the user decides how it is
resolved.

Execution is **phase-gated** per the brief's phasing (Foundation → People → Photos → Quality →
Readiness → Frigate enrollment → HA integration). Phases 1–5 are the actionable scope.
**Phase 6 (Frigate enrollment) is ⛔ BLOCKED pending explicit user approval** plus a
mandatory runtime API-verification task (T034). Phase 7 (HA integration) is designed-for but
not implemented. This matches feature 001's blocked-phase convention and the constitution's
Change Control (XI.1, XI.2).

## Technical Context

**Language/Version**: Python >= 3.11 (backend; Homebrew Python documented in quickstart if the
system interpreter is older); TypeScript (frontend). YAML for any config; Bash for test
convenience scripts.

**Primary Dependencies**:
- Backend: FastAPI, uvicorn, SQLAlchemy 2.0 (SQLite), Pydantic v2, python-multipart, Pillow,
  opencv-python-headless, numpy, imagehash (Phase 5), httpx + pytest (tests). All pinned
  (constitution VI.3).
- Frontend: React 18, Vite, TypeScript. Dev: Vite dev server proxying `/api` → FastAPI.
  POC run: `vite build` → static files served by FastAPI from one origin.
- Runtime integration (Phase 6 only): the running local Frigate 0.17.2 (`localhost:5001`),
  accessed exclusively through the `FrigateEnrollmentService` abstraction.
- Existing project tools reused as-is: ffmpeg (HEIC normalization), git.

**Storage**: `enrollment-app/data/` — SQLite DB (`app.db`) + `people/<person-uuid>/{original,
normalized, approved}/`. Entirely gitignored (defense-in-depth), never committed (constitution
II.4/II.5). Production storage requirements (backup, retention, permissions, deletion) are
documented in `docs/production/production-deployment.md`, not solved in the POC.

**Testing**: pytest (backend unit + API tests against the app's own SQLite/storage in temp
dirs); the frontend is validated via the quickstart walk-through (no separate JS test
framework in the MVP; Vite build is the compile check). Test fixtures are public-domain/
synthetic (scikit-image astronaut portrait + programmatic variants) — never household
biometric media (constitution II.4/II.5). Phase 6 tests mock the Frigate service first; real
integration tests only with explicit approval (brief: "mock first").

**Target Platform**: macOS (the confirmed Intel i9-9980HK POC host) — native venv process
bound to `127.0.0.1`. Never the Raspberry Pi 3 (constitution I.1/I.2, spec FR-001). The app
and biometric processing stay on the AI/compute host.

**Project Type**: Client/server web application (backend API + SPA frontend) — the first
application code in this repo (previously configuration-only, per CLAUDE.md).

**Performance Goals**: Uploads of up to ~10 photos return per-photo validation results within a
few seconds (YuNet face detection is CPU-fast; validation is synchronous in the MVP); UI
actions (create/edit/approve) feel instant (< 500 ms p95 locally). No hard SLA for a
single-user localhost app.

**Constraints**: localhost-only binding (never `0.0.0.0`); no silent enrollment; no identity
inference during quality validation; no automatic person creation from events; relationship
always user-supplied; no biometric media or secrets in git; existing 001 pipeline and Ring/HA
automations untouched (SC-012 regression); no invented Frigate endpoints (verified against
installed runtime).

**Scale/Scope**: Single household; a handful of people; tens of photos per person; single-user
localhost admin UI. No multi-user, no auth (POC), no LAN exposure.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design below.*

| Principle | Status | Notes |
|---|---|---|
| I.1 — HA remains the control plane | **PASS** | App runs on the AI host (Mac POC), never the Pi; HA automation work is Phase 7 and NOT implemented. |
| I.2 — AI workloads run separately | **PASS** | Enrollment app + biometric processing live on the compute host; Pi untouched. |
| I.3 — Local processing preferred | **PASS** | Everything localhost; no cloud storage, no cloud face services. |
| II.1 — Explicit enrollment only | **PASS** | Core of this feature: upload ≠ approve ≠ enroll; no import from events; FR-022/FR-027/FR-030. |
| II.2 — Unknown is the safe default | **PASS** | Quality thresholds favor review; readiness gate mirrors 001's conservative gate; app never weakens recognition thresholds. |
| II.3 — No physical-access control | **PASS** | The app is a management UI; recognition remains notification-only (001's FR-025 unchanged). |
| II.4 — Protect credentials/identity data | **PASS** | `enrollment-app/data/` gitignored with defense-in-depth; bytes on disk only; no secrets logged; test fixtures are non-biometric. |
| II.5 — Minimize retention | **PASS** | Explicit deletion of photos/person; enrollment removal removes Frigate identity; retention policy documented for production. |
| III.1 — Person detection comes first | **PASS** | Unchanged in 001's pipeline; the app doesn't touch detection order. |
| III.2 — Identity/relationship separate | **PASS** | The feature's design invariant; `display_name` ≠ `frigate_identity_name` ≠ relationship. |
| III.3 — Preserve the original security event | **PASS** | No interaction with 001's event path; SC-012 regression proves it. |
| IV.1 — AI failure must not break HA | **PASS** | App is additive and independent; if it or Frigate fails, 001's pipeline and HA automations are unaffected. |
| IV.2 — Every dependency needs a failure state | **PASS** | FRIGATE_UNAVAILABLE, FRIGATE_ENROLLMENT_FAILURE, STORAGE_FAILURE, DATABASE_FAILURE, decode≠no-face, FACE_DETECTOR_UNAVAILABLE (no silent detector fallback) — all explicit. |
| IV.3 — Don't treat unknown data as real data | **PASS** | `frigate.reachable: null` vs false; ERROR ≠ ENROLLED; decode failure ≠ NO_FACE. |
| V.4/V.5 — Reproducible tests & acceptance criteria | **PASS** | pytest + quickstart walk-through + SC-001–SC-014 in spec. |
| VI.1 — Minimize the stack | **JUSTIFIED DEVIATION** | The baseline stack has no management UI; a dedicated enrollment application is the brief's explicit new capability. Justification + simpler-alternative analysis in Complexity Tracking below. |
| VI.2 — Preferred dependencies | **PASS** | Reuses Frigate's own face detector (facedet.onnx) instead of a new model; ffmpeg already a project dependency. |
| VI.3 — Pin and document dependencies | **PASS** | Pinned requirements.txt; Frigate 0.17.2 API verified at T034 before any integration. |
| XI.1 — Requirements before implementation | **PASS** | Spec + plan + contracts precede any code; Phase 6 additionally gated on user approval. |
| XI.2 — Architecture changes require review | **PASS** | Adding the first application to the repo is a documented change under this feature's own review; no public exposure; no biometric data externally retained. |

No unjustified violations. **Complexity Tracking** (below) records the one justified deviation
(VI.1) and the open decisions requiring user approval.

**Post-Phase-1 re-check**: `data-model.md`, `contracts/`, and `quickstart.md` were reviewed
against the table after drafting. No new violations: the REST contract stays loopback-only
(II.4), the quality pipeline performs no identity inference (II.1), the Frigate abstraction
keeps all integration behind one service and gated (II.1, VI.3), and the quickstart validates
phases 1–5 without touching Frigate's library (II.1, III.2). Gate remains **PASS**.

## Project Structure

### Documentation (this feature)

```text
specs/002-known-person-enrollment-manager/
├── spec.md                       # Feature specification (user brief rulings encoded)
├── plan.md                       # This file
├── research.md                   # Phase 0 output (decisions + open decisions)
├── data-model.md                 # Phase 1 output (Person, EnrollmentPhoto, AuditLog, states)
├── quickstart.md                 # Phase 1 output (validation guide for phases 1–5)
├── contracts/                    # Phase 1 output
│   ├── rest-api.md               # App REST API contract
│   ├── photo-quality.md          # Quality pipeline, states, reasons, thresholds, readiness
│   └── frigate-enrollment-interface.md  # Frigate service abstraction (Phase 6 design basis)
├── checklists/
│   └── requirements.md           # Spec quality checklist (PASS)
├── validation-report.md          # To be produced by implementation (living document)
└── tasks.md                      # Phase 2 output (/speckit-tasks — not created by this command)
```

### Source Code (repository root)

```text
enrollment-app/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app factory, 127.0.0.1 binding, static SPA serving
│   │   ├── config.py             # Settings (paths, thresholds, relationships list)
│   │   ├── db.py                 # SQLAlchemy engine/session; SQLite at data/app.db
│   │   ├── models/               # Person, EnrollmentPhoto, AuditLogEntry
│   │   ├── api/                  # routers: people, photos, readiness, audit, relationships,
│   │   │                         #   health, frigate (Phase 6), errors.py (error envelope)
│   │   ├── services/
│   │   │   ├── person_service.py     # CRUD + disable/enable + delete lifecycle
│   │   │   ├── photo_service.py      # upload, metadata, delete, approval
│   │   │   ├── quality_service.py    # validation pipeline (photo-quality.md)
│   │   │   ├── face_detector.py      # YuNet (facedet.onnx); NO fallback detector
│   │   │   ├── readiness_service.py  # readiness calc (>= 5 suitable approved)
│   │   │   ├── storage_service.py    # data/ paths, UUID dirs, traversal-safe
│   │   │   ├── audit_service.py      # audit log writes
│   │   │   └── frigate_service.py    # FrigateEnrollmentService (Phase 6, blocked)
│   │   └── tests/                    # pytest; fixtures = public-domain/synthetic images
│   │       ├── conftest.py
│   │       ├── fixtures/             # generated at test time, not committed binaries
│   │       ├── test_people.py
│   │       ├── test_photos.py
│   │       ├── test_quality.py
│   │       ├── test_readiness.py
│   │       ├── test_privacy.py       # gitignore + deletion-artifact assertions
│   │       └── test_frigate_mock.py  # Phase 6 (mock service)
│   ├── requirements.txt          # pinned backend deps
│   └── run.sh                    # venv bootstrap + uvicorn on 127.0.0.1:8000
├── frontend/
│   ├── src/
│   │   ├── App.tsx / main.tsx
│   │   ├── api/client.ts         # typed fetch wrapper against contracts/rest-api.md
│   │   ├── pages/                # PeoplePage, PersonDetailPage, AddPersonPage
│   │   └── components/           # PersonCard, PhotoGrid, PhotoCard, ReadinessBadge,
│   │                             #   UploadDropzone, AuditLogView
│   ├── vite.config.ts            # dev proxy /api → http://127.0.0.1:8000
│   └── package.json
├── data/                         # PRIVATE — gitignored (app.db + people/<uuid>/...)
└── README.md                     # how to run the app locally
```

**Structure Decision**: The brief's proposed `enrollment-app/{frontend,backend,data}` layout
fits the repo directly (repo root currently has only config/docs/tests, no `src/`). The
backend is organized as a small FastAPI service (models/api/services split), per the brief's
`app/{api,models,services}` example. `enrollment-app/data/` is the sole private writable tree
and is gitignored with defense-in-depth. No existing directory is moved or repurposed:
feature 001's `tests/phase1/test-media/photos/` is NOT adopted as app storage (research.md #7
— existing photos are not moved; the user re-uploads through the app).

## Open decisions requiring user approval

1. **Hosting mode** — native venv (recommended default) vs. Docker Compose service. Native
   chosen; containerization remains the production option (research.md #1).
2. **Frontend framework** — React + Vite SPA (recommended default) vs. Next.js. Vite chosen
   (research.md #2).
3. **Face-detection engine** — reuse Frigate's `facedet.onnx` (YuNet) via OpenCV (recommended
   default) vs. another detector. **RESOLVED 2026-09-10 (user-approved): YuNet only, NO
   fallback detector** — missing/unloadable model → `FACE_DETECTOR_UNAVAILABLE` (research.md
   #3; Phase 4 G4).
4. **Delete-with-enrollment semantics** — refuse delete until enrollment removed explicitly
   (recommended default; FR-026) vs. cascade-delete with a single confirmation.
5. **Phase 6 execution approval** — required before any Frigate integration task runs
   (FR-030). Not requested now; this plan keeps it blocked.

## Complexity Tracking

| Violation / Deviation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| VI.1 — new application added to the baseline stack | The brief explicitly requires a local management UI for the known-person library; no existing component (Frigate NVR UI, HA automations, config files) can safely provide photo upload, objective quality validation, approval, readiness, and enrollment orchestration. This is the first application code in the repo — a deliberate, reviewed addition under XI.2. | Manually managing photos + a spreadsheet (the status quo that produced the T034 gate) — rejected: exactly the failure mode this feature fixes; Home Assistant automations as the management surface — rejected: HA is the runtime control plane (I.1), not an admin UI, and face-quality validation needs local compute tools (OpenCV/Pillow) that belong on the AI host. |
| Frigate integration exists at all (Phase 6) | The brief requires eventual enrollment into Frigate's native library and explicitly warns against container-local face storage; the abstraction + mock-first testing keeps this additive and reviewable. | Writing faces directly into Frigate's data volume — rejected: bypasses Frigate's own library management and the explicit-approval rule. |

No other gate failures. Everything else passes as documented in the Constitution Check table.