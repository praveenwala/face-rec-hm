---
description: "Task list for Known Person Enrollment Manager"
---

# Tasks: Known Person Enrollment Manager

**Input**: Design documents from `/specs/002-known-person-enrollment-manager/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md —
all present.

**Tests**: Included. The brief explicitly requires tests (People, Photos, Readiness, Privacy,
Frigate mock-first); unit/API tests live in `enrollment-app/backend/app/tests/` via pytest.

**Organization — deviation from the default template**: Tasks are grouped by the brief's
**implementation phases (1–7)**, not by spec user-story priority alone. This mirrors feature
001's phase-gating convention (constitution V.1, XI.1): US7 (enroll into Frigate) is P1/P2 in
the spec but is ⛔ **BLOCKED** here until the user explicitly approves executing Phase 6 and
task T034 (Frigate 0.17.2 API verification against the installed runtime) passes. Phase 7 (HA
integration) is design-only, never executed in this feature. Every task carries its `[USn]`
label for spec traceability.

**Cross-feature invariants (must never be violated by any task)**:
- Do NOT execute feature 001's T034; do NOT enroll anyone; do NOT modify 001's Frigate
  config, MQTT wiring, Ring/HA automations, or `tests/phase1/test-media/photos`.
- Do NOT expose the app beyond `127.0.0.1`.
- Do NOT commit or push without user review.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US8 from spec.md. Omitted for Setup/Foundational/Polish tasks.

---

## Phase 1: Foundation

**Purpose**: Backend + frontend skeletons, SQLite, private storage, localhost binding, audit
logging, error envelope, and the Phase 1 gate.

- [x] T001 Create `enrollment-app/` structure per `plan.md`'s Project Structure; add
  defense-in-depth `.gitignore` rules: `enrollment-app/data/`, `enrollment-app/backend/.venv/`,
  `enrollment-app/frontend/node_modules/`, `enrollment-app/frontend/dist/`, `*.sqlite*` —
  **DONE 2026-09-10**: rules added (plus `__pycache__/`, `*.py[cod]`, `.pytest_cache/`);
  `git check-ignore` verified for data, .venv, node_modules, dist
- [x] T002 [P] Backend skeleton: FastAPI app factory, uvicorn bound to `127.0.0.1:8000` only
  (`enrollment-app/backend/app/main.py`, `run.sh`), `GET /api/health` (contracts/rest-api.md) —
  **PASS**: `run.sh` boots uvicorn on `127.0.0.1:8000` (lsof + uvicorn log confirm loopback
  only); `/api/health` → `{"status":"ok","database":"ok","frigate":{"reachable":null}}`
- [x] T003 [P] SQLite + SQLAlchemy 2.0 setup with `Person`, `EnrollmentPhoto`,
  `AuditLogEntry` models per `data-model.md` (`app/db.py`, `app/models/`); schema created on
  startup (Alembic migrations deferred to production) — **PASS**: tables created at
  `enrollment-app/data/app.db`; `Person.frigate_identity_name` unique + nullable;
  `AuditLogEntry` uses `entity_type`/`entity_id` per the approved implementation instruction
  (data-model.md updated to match)
- [x] T004 [P] `StorageService` (`app/services/storage_service.py`): `data/` layout
  `people/<uuid>/{original,normalized,approved}/`, randomized filenames, traversal-safe path
  construction; refuses writes outside `enrollment-app/data/` — **PASS**: UUID dirs,
  randomized UUID filenames (display names never used as paths), `resolve_inside` rejects
  escapes; tests cover traversal + write confinement + deletion
- [x] T005 [P] `AuditService` (`app/services/audit_service.py`): append-only audit log with the
  action enum from `data-model.md`; never logs image bytes or secrets (FR-031) — **PASS**: full
  `AuditAction` enum defined; record+read-back test green
- [x] T006 [P] Error envelope + exception mapping (`app/api/errors.py`): codes
  `MEDIA_DECODE_FAILURE`, `NO_FACE_DETECTED`, `MULTIPLE_FACES`, `FACE_TOO_SMALL`,
  `QUALITY_REJECTED`, `STORAGE_FAILURE`, `DATABASE_FAILURE`, `FRIGATE_UNAVAILABLE`,
  `FRIGATE_ENROLLMENT_FAILURE`, `IDENTITY_CONFLICT` per `contracts/rest-api.md` — **PASS**:
  envelope + handlers wired; Phase 6 routes return explicit `501 FEATURE_NOT_ENABLED`
  (`app/api/future.py`) — never fake enrollment
- [x] T007 [P] Frontend skeleton: Vite + React + TypeScript (`enrollment-app/frontend/`),
  dev proxy `/api` → `127.0.0.1:8000`, typed API client (`src/api/client.ts`) against
  `contracts/rest-api.md` — **PASS**: `npm run build` clean; dev server on `127.0.0.1:5173`
  (loopback only, lsof-confirmed); `/api` proxy verified against the live backend; UI shows
  health badge + visibly disabled "Enrollment not enabled in this phase" control
- [x] T008 [P] Tests: health endpoint, loopback-only binding assertion (SC-011), storage
  isolation (writes confined to `data/`), audit write, gitignore check for
  `enrollment-app/data/` — **PASS**: `pytest` → **17 passed** (incl. real uvicorn subprocess
  boot on loopback + `git check-ignore` privacy tests); 001 harness `run_harness.sh all` →
  **OVERALL PASS** unchanged (SC-012)

**Checkpoint (Gate G1) — PASS 2026-09-10**: App boots on `127.0.0.1` only; DB + private
storage isolated; `git status` shows no data content; `pytest` green. Phase 2 is actionable
pending user review (see validation-report.md Phase 1 section).

---

## Phase 2: People Management

**Purpose**: Create/edit/disable/delete people with relationship categories (US1, US5, US6).

- [x] T009 [US1] Relationship categories as a config list + `GET /api/relationships`
  (`app/config.py`; FR-004) — **DONE 2026-09-10**: `app/api/system.py` returns
  `{"relationships": ["Family","Friend","Neighbor","Other Known"]}`; Pydantic enum
  validates membership (400 VALIDATION_ERROR)
- [x] T010 [US1] `PersonService` + endpoints `GET/POST /api/people`, `GET/PATCH/DELETE
  /api/people/{id}` (`app/services/person_service.py`, `app/api/people.py`) with validation
  (display name required; relationship from the list; FR-003/FR-005) — **DONE**: CRUD live;
  UUID server-generated; malformed UUID → 400, unknown → 404; `extra="forbid"` on PATCH;
  fix: validation handler now JSON-sanitizes Pydantic `ctx` exceptions
- [x] T011 [US5] Disable/enable via `PATCH {enabled}`; disabled preserves the record, distinct
  from delete and from enrollment removal (FR-025; `data-model.md` invariants) — **DONE**:
  toggle live, record preserved; PERSON_ENABLED/DISABLED audited
- [x] T012 [US5] Delete lifecycle: `DELETE /api/people/{id}` removes person + photo rows +
  stored files; refuses when `enrollment_status == ENROLLED` unless `remove_enrollment=true`
  (FR-026; enforced in service, not just UI) — **DONE**: photo rows cascade (FK
  ondelete=CASCADE; file removal is Phase 3); **Phase-2 deviation**: delete is refused
  (409 ENROLLED_PERSON_DELETE_REFUSED) whenever ENROLLED, even with
  `remove_enrollment=true`, because Phase 6 removal is blocked — documented in
  contracts/rest-api.md; branch exercised by direct-DB test
- [x] T013 [US1] Audit wiring: `PERSON_CREATED/UPDATED/DISABLED/ENABLED/DELETED`,
  `RELATIONSHIP_CHANGED` (FR-031) — **DONE**: all six events + `GET /api/audit`
  (newest-first, `entity_type`/`entity_id`, details JSON only)
- [x] T014 [US6] UI: People page grouped by relationship (US6), Add Person form, edit,
  disable/enable, delete with confirmation (`src/pages/PeoplePage.tsx`, `AddPersonPage.tsx`) —
  **DONE**: grouped cards (Family/Friends/Neighbors/Other Known), edit modal, delete
  confirmation distinguishing Delete vs Disable, no fabricated photos
- [x] T015 [US5] Tests: person create, edit, relationship assignment/change, disable
  (preserved), delete (record + photos + files gone), invalid relationship rejected (spec
  testing list) — **DONE**: `test_people.py` (32 tests); `pytest` → **49 passed** total

**Checkpoint (Gate G2) — PASS 2026-09-10**: People CRUD + grouping work in UI and API;
audit entries present; 001 harness OVERALL PASS unchanged; nothing committed/pushed.

---

## Phase 3: Photo Management

**Purpose**: Multi-file upload, private storage, thumbnails, photo delete (US2).

- [x] T016 [US2] Upload endpoint `POST /api/people/{id}/photos` (multipart, multi-file):
  size check (20 MB default), content sniff, store original untouched (FR-010/FR-011);
  returns one result object per file (contracts/rest-api.md)
- [x] T017 [P] [US2] Photo metadata extraction (Pillow): dimensions, mime by content, EXIF
  orientation recorded (`app/services/photo_service.py`; `data-model.md` EnrollmentPhoto)
- [x] T018 [P] [US2] File + thumbnail endpoints (`.../file?kind=original|normalized`,
  `.../thumbnail`, max ~300px) — loopback only
- [x] T019 [US2] Photo delete: DB row + `original/` + `normalized/` files removed (US2
  scenario 4); audit `PHOTO_DELETED`
- [x] T020 [US2] UI: drag-and-drop multi-upload dropzone, per-photo result list, thumbnails,
  delete (`src/components/UploadDropzone.tsx`, `PhotoGrid.tsx`)
- [x] T021 [US2] Tests: valid multi-upload (all stored + listed), delete photo (row + files
  gone)

**Checkpoint (Gate G3)**: Photos upload, list, thumbnail, and delete end-to-end; originals
never altered.

---

## Phase 4: Quality Validation

**Purpose**: Objective per-photo validation with explicit classifications (US3) per
`contracts/photo-quality.md`.

- [x] T022 [P] [US3] `FaceDetector` (`app/services/face_detector.py`): load Frigate's
  `facedet.onnx` (YuNet via OpenCV FaceDetectorYN) — **DONE 2026-09-10**: app-owned copy at
  `enrollment-app/data/models/facedet.onnx` (gitignored; `scripts/fetch_models.sh` downloads
  from `NickM-27/facenet-onnx` v1.0 — Apache-2.0, the same release Frigate 0.17.2 uses;
  sha256 `321aa5a6…9294` verified, never a path inside the running Frigate container);
  **no silent Haar fallback** (user-approved Phase 4 decision): missing/unloadable model →
  `FACE_DETECTOR_UNAVAILABLE` (503 on re-analysis; upload degrades to PENDING with an
  explicit `analysis_error`), readiness semantics never silently change detector
- [x] T023 [P] [US3] Face size + count checks: `face_count`, `face_size_ratio` (area +
  per-axis); `face_count == 0` → `NO_FACE`; `face_count > 1` →
  `REVIEW_REQUIRED`/`MULTIPLE_FACES` (FR-016/FR-017) — **DONE**: deterministic precedence in
  `PhotoQualityService._analyze_bytes`; multi-face is a hard stop with an explicit
  "only the intended person" note; no auto-select/crop
- [x] T024 [P] [US3] Sharpness (Laplacian variance) + brightness (mean luminance) + orientation
  checks → `TOO_BLURRY`/`UNDEREXPOSED`/`OVEREXPOSED` (FR-012/FR-014) — **DONE**: measured over
  the face crop; thresholds in `QualityConfig` (`min_sharpness_laplacian=40.0`,
  `brightness_min=40.0`, `brightness_max=220.0`) — initial conservative baselines, NOT
  claimed as tuned (T033-style stance); exposure never phrased as day/night/indoor
- [x] T025 [P] [US3] HEIC/HEIF normalization via ffmpeg → JPEG into `normalized/` — ⛔
  **DEFERRED** (unchanged): HEIC stays `UNSUPPORTED_FORMAT` with the explicit convert note;
  no silent normalization; no `normalized/` artifact is produced in Phase 4 and
  `kind=normalized` returns an honest 404
- [x] T026 [US3] `PhotoQualityService` pipeline (`app/services/quality_service.py`) wired into
  upload: automatic per-photo analysis → `quality_status` + `rejection_reason` +
  measurements/rejection_details (FR-015/FR-016; objective vs. heuristic split); explicit
  re-analysis via `POST /api/people/{id}/photos/{photo_id}/analyze` — **DONE**: original
  bytes never modified (in-memory EXIF-transposed working copy); `SUITABLE` never implies
  approval/enrollment (those fields are never touched by analysis)
- [x] T027 [US3] UI: per-photo status badges (✓ Suitable / ✕ Unsuitable / ⚠ Review required /
  Pending) + reason + expandable measurements rendered separately from judgments
  (US3 scenario 6) — **DONE**: `PhotoGrid.tsx` badge classes, human-readable reasons,
  details `<dl>` (face count, face size %, sharpness, brightness, note), multi-face guidance,
  Re-analyze action
- [x] T028 [US3] Tests — **DONE**: `test_quality.py` (20 tests): valid upload → SUITABLE;
  corrupt stored file → `MEDIA_DECODE_FAILURE` (never `NO_FACE`); no face → `NO_FACE`;
  tiny face → `FACE_TOO_SMALL`; multiple faces → `REVIEW_REQUIRED`; blur/exposure fixtures;
  missing model → explicit `FACE_DETECTOR_UNAVAILABLE` (upload PENDING + 503 re-analysis);
  no silent fallback; approval/enrollment boundaries (never approved/enrolled, no Frigate
  calls); original byte-for-byte untouched; no normalized artifact; fixtures are the single
  public-domain astronaut.png (NASA, scikit-image sample) + derived synthetic images
  (fixtures/README.md)

**Checkpoint (Gate G4) — PASS 2026-09-10**: Every upload receives an explicit
classification; no generic "upload failed"; multi-face never silently accepted. `pytest` →
**98 passed**; 001 harness `run_harness.sh all` → **OVERALL PASS** unchanged. See
validation-report.md Phase 4 section. Phase 5 actionable pending user review.

---

## Phase 5: Enrollment Readiness

**Purpose**: Approval + readiness gate (US4) and near-duplicate detection (US3 bonus), the
functionality that resolves the 001-T034 media-gate need.

- [x] T029 [P] [US4] `ReadinessService` + `GET /api/people/{id}/readiness`:
  `approved_suitable_count = count(SUITABLE AND approved, exact-duplicate groups counted
  once)`, `required_min = 5`, `DRAFT/NOT_READY/READY`, `missing` list, `diversity` review
  object (`contracts/photo-quality.md`) — **DONE 2026-09-10**: `app/services/readiness_service.py`;
  response per the approved Phase 5 shape (`person_id`, `status`, `minimum_required`,
  `approved_suitable_count`, `remaining_required`, `total_uploaded`, `suitable_count`,
  `approved_count`, `review_required_count`, `unsuitable_count`, `enrollment_enabled:
  false`, `missing`, `diversity`); no private paths; person summaries reuse the deduped count
- [x] T030 [P] [US4] Photo approval: `POST /api/people/{id}/photos/{photo_id}/approve` /
  `.../unapprove`; approval is explicit, never automatic (FR-019/FR-023); only
  `SUITABLE` may be approved, anything else → `409 PHOTO_NOT_APPROVABLE`; approve/unapprove
  idempotent; audit `PHOTO_APPROVED` / `PHOTO_UNAPPROVED`; readiness recomputes — **DONE**:
  `PhotoService.approve/unapprove` + endpoints; `approved` is metadata only (never touches
  quality analysis); reanalysis that degrades a previously approved photo auto-clears
  approval (audited `PHOTO_UNAPPROVED`), detector-failure during reanalysis preserves the
  prior result and approval
- [x] T031 [US3] Duplicate handling: exact SHA-256 `duplicate_group` assigned at upload;
  only one member of an exact-duplicate group counts toward readiness (byte-identical ×5
  can never reach READY); near-duplicate detection via perceptual hash (pHash, Hamming
  distance ≤ 8) is **advisory only** — it never changes `quality_status` (a near-duplicate
  stays SUITABLE), never blocks approval, never auto-deletes, never identity similarity
  (research.md #5, Phase 5; user's G5 near-duplicate semantics) — **DONE**:
  `app/services/duplicate_service.py` + quality-service pHash advisory
  (`near_duplicate_advisory` in measurements, `near_duplicate` in photo summaries,
  `near_duplicate_advisory` flag in readiness response); both near-duplicate photos may be
  approved and both count toward the ≥ 5 gate
- [x] T032 [P] [US4] UI: readiness card ("3 / 5 approved suitable photos — NOT READY" /
  "READY FOR ENROLLMENT") + explicit Approve/Unapprove actions on SUITABLE photos only;
  contextual disabled enrollment control (NOT_READY: "Enrollment unavailable — at least 5
  approved suitable photos required"; READY: "Ready for enrollment — enrollment is not
  enabled in this phase"); no auto-enroll behavior anywhere (SC-006); people cards show
  photo count + approved-suitable count + readiness status (never "Enrolled") — **DONE**:
  `PersonDetailPage.tsx`, `PhotoGrid.tsx`, `PeoplePage.tsx`, `App.tsx`
- [x] T033 [US4] Tests — **DONE**: `test_readiness.py` (17 tests): approval rules
  (SUITABLE yes; PENDING/UNSUITABLE/REVIEW_REQUIRED → PHOTO_NOT_APPROVABLE; idempotent;
  cross-person blocked; quality_status never changed by approval), readiness cases
  (0/1/4 → NOT_READY, 5/6+ → READY, 5 suitable but 4 approved → NOT_READY, unsuitable and
  review-required never count, delete/unapprove recalculate, re-approving fifth → READY),
  exact-duplicate inflation blocked, degrading reanalysis clears approval + recalculates,
  detector-failure during reanalysis preserves prior state/approval, READY transition makes
  zero Frigate/embedding/MQTT/HA calls with `frigate_identity_name` NULL and
  `enrolled_in_frigate` false; privacy tests — uploaded files untracked, `data/`
  gitignored, deletion removes expected artifacts (SC-007); all fixtures synthetic/
  public-domain (astronaut.png derived variants)

**Checkpoint (Gate G5) — PASS 2026-09-10**: Readiness gate matches the 001-T034 requirement
(≥ 5 distinct approved suitable photos); exact duplicates cannot inflate readiness;
near-duplicates are advisory only (stay SUITABLE, approvable, count toward the gate — never
REVIEW_REQUIRED solely for similarity); READY never auto-enrolls (zero
Frigate/embedding/MQTT/HA calls verified by test). `pytest` → **116 passed**; 001 harness
`run_harness.sh all` → **OVERALL PASS** unchanged. This is the evidence the user may use to
decide feature 001's T034 disposition. Nothing committed/pushed pending user review.

---

## Phase 6: Frigate Enrollment — ⛔ BLOCKED

**⛔ BLOCKED until the user explicitly approves executing this phase AND task T034 (Frigate
API verification) passes.** Execution requires: (a) explicit user approval (FR-030),
(b) task T034 completing first (Frigate 0.17.2 API verification against the installed
runtime), (c) the disposition decision for feature 001's T034 task. Do NOT start early.

- [ ] T034 [US7] Verify the Frigate 0.17.2 face API from the installed runtime
  (`GET http://localhost:5001/api/openapi.json`): confirm `GET /api/faces`,
  `POST /api/faces/{name}/create`, `POST /api/faces/{name}/register`,
  `POST /api/faces/train/{name}/classify`, `POST /api/faces/{name}/delete`,
  `POST /api/faces/reprocess`, `POST /api/faces/recognize`, `PUT /api/reindex` + exact
  payloads; update `contracts/frigate-enrollment-interface.md` with verified facts
  (FR-029, VI.3)
- [ ] T035 [US7] `FrigateEnrollmentService` (`app/services/frigate_service.py`): health, list
  identities, create, register, train, delete, reindex, reconcile — all behind the one
  abstraction (FR-028)
- [ ] T036 [P] [US7] `POST /api/people/{id}/enroll` (explicit action; `READY` required;
  `ENROLLING → ENROLLED | ERROR`; IDENTITY_CONFLICT on duplicate `frigate_identity_name`;
  marks submitted photos `enrolled_in_frigate`) + audit `ENROLLMENT_REQUESTED/COMPLETED/
  FAILED`
- [ ] T037 [P] [US8] `DELETE /api/people/{id}/enrollment` (removes identity, resets status,
  audit `ENROLLMENT_REMOVED`) + `GET /api/frigate/status` (health + identities,
  reconciliation source)
- [ ] T038 [US7] `reconcile()`: app vs. Frigate drift surfaced, never auto-mutated (II.1)
- [ ] T039 [US7] Enroll UI: "Enroll Approved Photos" button (only when READY), progress,
  error states, remove-enrollment action
- [ ] T040 [US7] Tests: Frigate service mocked — enrollment happy path, NOT_READY refusal,
  IDENTITY_CONFLICT, FRIGATE_UNAVAILABLE, partial-failure → ERROR, remove enrollment,
  delete-with-enrollment refusal (spec: "mock first")
- [ ] T041 [US7] Real integration test against the live local Frigate — **ONLY with explicit
  user approval** (spec: "real integration test only when explicitly approved")

**Checkpoint (Gate G6)**: Enrollment works against the verified 0.17.2 API with mock-verified
failure paths; real integration evidence only if approved. Feature 001's T034 disposition is
decided by the user before or at this gate.

---

## Phase 7: Home Assistant Integration — ⛔ NOT IMPLEMENTED

**Design-only. No tasks are actionable.** Future scope (identity = Praveen, relationship =
Family → HA notification enrichment) belongs to feature 001's Phase 6 (HA Intelligence) or a
future feature. Existing Ring automations must remain completely independent. This phase is
listed for continuity and MUST NOT be executed by this feature.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T042 [P] `enrollment-app/README.md` (how to run, localhost-only statement, auth
  boundary — auth becomes mandatory before any LAN/production access, research.md #11)
- [ ] T043 [P] Document pinned dependency versions (backend requirements, frontend packages)
  per constitution VI.3
- [ ] T044 Re-run `quickstart.md` end-to-end as a final regression (phases 1–5)
- [ ] T045 Re-run `tests/phase1/run_harness.sh all` and confirm `OVERALL PASS` unchanged
  (SC-012)
- [ ] T046 [P] Document production storage requirements (backup, retention, permissions,
  deletion) in `docs/production/production-deployment.md` (brief: production storage warning)
- [ ] T047 Final gitignore audit: `git status` clean of any biometric/data content (SC-007);
  confirm no `enrollment-app/data/` content tracked

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundation)**: No dependencies — can start immediately.
- **Phase 2 (People)**: Depends on Gate G1.
- **Phase 3 (Photos)**: Depends on Gate G2.
- **Phase 4 (Quality)**: Depends on Gate G3.
- **Phase 5 (Readiness)**: Depends on Gate G4.
- **Phase 6 (Frigate Enrollment)**: Depends on Gate G5 **AND explicit user approval AND task
  T034 (API verification) passing AND the 001-T034 disposition decision**.
- **Phase 7 (HA Integration)**: NEVER executed by this feature.
- **Phase 8 (Polish)**: Depends on whichever phase execution stops at (G5 for the
  not-yet-approved scope).

### User Story Dependencies

- **US1 (P1)**: Phase 2. No dependency on other stories.
- **US2 (P1)**: Phase 3. Depends on US1.
- **US3 (P1)**: Phase 4. Depends on US2 (validation consumes uploaded photos).
- **US4 (P1)**: Phase 5. Depends on US3 (readiness consumes quality status) + approval
  (T030).
- **US5 (P2)**: Phase 2 (CRUD) + Phase 6 (enroll-aware delete). Split by design.
- **US6 (P2)**: Phase 2. Depends on US1 (grouping consumes relationship metadata).
- **US7 (P1/P2)**: Phase 6 — planned and designed now but ⛔ BLOCKED (approval + task T034).
- **US8 (P2)**: Phase 6 — removal lifecycle; blocked with US7.

### Within Each Phase

- Services before endpoints; endpoints before UI; tests written alongside the implementation
  they validate (feature 001 convention — integration-style assertions, not strict red-green
  for the API tests).
- Storage/DB isolation is exercised at every phase (nothing ever writes outside
  `enrollment-app/data/`).

### Parallel Opportunities

- Phase 1: T002–T008 are independent files ([P]).
- Phase 3: T017/T018 (metadata + file serving) parallel.
- Phase 4: T022–T025 (detector, size checks, sharpness/brightness, HEIC) parallel; T026
  integrates.
- Phase 5: T029/T030 parallel; T032 UI after readiness service.
- Phase 6: T036/T037 parallel once the service (T035) exists.

---

## Parallel Example: Phase 1 Foundation

```bash
# After T001 creates the structure, launch together:
Task: "FastAPI app factory + /api/health on 127.0.0.1:8000"
Task: "SQLite + SQLAlchemy models (Person, EnrollmentPhoto, AuditLogEntry)"
Task: "StorageService with traversal-safe data/ layout"
Task: "AuditService append-only log"
Task: "Error envelope + exception mapping"
Task: "Vite + React + TypeScript skeleton with /api proxy"
```

---

## Implementation Strategy

### MVP First (Phases 1–5 only)

1. Complete Phase 1 (Foundation) → Gate G1
2. Complete Phase 2 (People) → Gate G2
3. Complete Phase 3 (Photos) → Gate G3
4. Complete Phase 4 (Quality) → Gate G4
5. Complete Phase 5 (Readiness) → Gate G5
6. **STOP and VALIDATE**: run `quickstart.md` end-to-end; confirm SC-001–SC-013 for the
   not-yet-approved scope; present readiness evidence for the 001-T034 decision
7. Do NOT proceed to Phase 6 without explicit user approval

### Incremental Delivery (once unblocked)

1. Phases 1–5 → the local management surface replaces the manual photo workflow
2. Phase 6 (approved) → explicit enrollment into Frigate with mock-verified failure paths
3. Phase 7 → never in this feature (design handed to future HA work)

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks.
- [Story] label maps a task to its spec.md user story; omitted for Setup/Polish tasks.
- Gates G1–G6 are hard stops (constitution V.1/XI.1). **Gate G6 additionally requires the
  user's explicit approval before any Frigate integration task runs (FR-030).**
- Commit after each task or logical group — but never without user review (per the brief).
- `validation-report.md` is a living document (feature 001 convention) — update it as each
  phase completes; record quality-threshold tuning in it when real household photos are
  validated (never silently, constitution II.2).
- Feature 001's `tasks.md`/`validation-report.md` must remain untouched by this feature's
  tasks; feature 001's T034 status changes only by the user's explicit decision.