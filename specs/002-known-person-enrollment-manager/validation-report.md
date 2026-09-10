# Validation Report: Known Person Enrollment Manager

**Feature**: [Known Person Enrollment Manager](./spec.md)
**Date**: 2026-09-10
**Executed by**: Claude Code, per tasks T001–T021 (Phases 1–3)

This is a living document (feature 001 convention): update it, don't recreate it, as each
phase completes.

## Phase 1 (Foundation) — Gate G1

**Status: PASS — 2026-09-10.** Backend + frontend skeletons, SQLite, private storage,
audit logging, error envelope, and loopback-only binding are implemented and verified.

### Environment

| Tool | Version | Notes |
|---|---|---|
| Python | 3.13.0 | venv at `enrollment-app/backend/.venv` |
| Node / npm | v22.23.1 / 10.9.8 | Vite 6 + React 18 + TypeScript 5.6 |
| Backend deps (pinned floors, exact versions) | fastapi 0.141.1, uvicorn 0.52.4, SQLAlchemy 2.0.52, pydantic 2.13.5, pillow 12.3.0, python-multipart 0.0.32, pytest 9.1.1, httpx 0.28.1 | Exact-pin freeze is Phase 8 (T043) scope |

### T001 — Structure + gitignore

- `enrollment-app/{backend,frontend,data}` created; backend `app/{models,api,services,tests}`,
  frontend `src/{api,components(pending),pages(pending)}`.
- `.gitignore` defense-in-depth added: `enrollment-app/data/`, `backend/.venv/`,
  `frontend/node_modules/`, `frontend/dist/`, `__pycache__/`, `*.py[cod]`, `.pytest_cache/`.
  Verified: `git check-ignore` matches `enrollment-app/data/app.db`,
  `enrollment-app/data/people/<uuid>/original/x.jpg`, `.venv/bin/python`, `node_modules/...`,
  `dist/index.html` (exit 0 for each). The repo's global `*.db`/`*.jpg`/`*.png` patterns
  backstop the data path (defense-in-depth confirmed).

### T002–T003 — Backend + database

- FastAPI app factory (`app/main.py`), `GET /api/health` → `{"status":"ok",
  "app_version":"0.1.0","database":"ok","frigate":{"reachable":null}}` (frigate reachability
  deliberately null pre-Phase-6 — constitution IV.3).
- `run.sh` bootstraps the venv on first run and starts uvicorn on `127.0.0.1:8000` only.
- SQLite at `enrollment-app/data/app.db`; tables `people`, `enrollment_photos`,
  `audit_log` created on startup. Models per `data-model.md`; `AuditLogEntry` uses
  `entity_type`/`entity_id` per the user-approved implementation instruction (data-model.md
  updated to match). `Person.frigate_identity_name` unique + nullable (NULL until Phase 6).

### T004–T006 — Storage, audit, errors

- `StorageService`: `people/<uuid>/{original,normalized,approved}/`, randomized UUID
  filenames (display names never used as paths), atomic writes, traversal-safe
  `resolve_inside` that raises `STORAGE_FAILURE` on any escape.
- `AuditService`: append-only `audit_log` with the full `AuditAction` enum; details are
  JSON metadata only (no image bytes, no secrets — FR-031).
- Error envelope `{"error":{code,message,details}}` with handlers for AppError,
  RequestValidationError (→ VALIDATION_ERROR), and unhandled (→ INTERNAL_ERROR, logged).
  Phase 6 enrollment routes return explicit `501 FEATURE_NOT_ENABLED`
  (`app/api/future.py`) — never fake enrollment (spec FR-030).

### T007 — Frontend

- Vite 6 + React 18 + TypeScript, `server.host: '127.0.0.1'`, port 5173, `/api` proxy →
  `127.0.0.1:8000`. Typed client (`src/api/client.ts`) parses the error envelope.
- `npm run build` clean (tsc + vite). Dev server serves the shell at 127.0.0.1:5173 with a
  live health badge and a visibly disabled "Enrollment not enabled in this phase" control
  (per the approved implementation instruction — no misleading controls).

### T008 — Tests

`python -m pytest app/tests -v` → **17 passed**:

| Area | Result |
|---|---|
| Health (liveness + SQLite + 501 stubs) | PASS (3) |
| Storage (UUID dirs, randomized names, traversal rejection, write confinement, deletions) | PASS (6) |
| Audit (record/read-back, append-only, no byte-bearing columns) | PASS (2) |
| Network (run.sh binds 127.0.0.1 only; real uvicorn subprocess serves health on loopback) | PASS (3) |
| Privacy (data path + tooling dirs gitignored; default data dir under enrollment-app/) | PASS (5) |

### Networking evidence (SC-011)

- `lsof -nP -iTCP -sTCP:LISTEN`: backend `TCP 127.0.0.1:8000`, frontend
  `TCP 127.0.0.1:5173` — no `*`/`0.0.0.0` listeners from the app.
- Observation: during the first smoke test, an unrelated pre-existing python process
  (`PID 56611`, started before this work) was briefly listening on `*:8000`; it exited on
  its own and was not part of the enrollment app (the app's own listener was
  `127.0.0.1:8000`, confirmed by uvicorn log + lsof). Noted for awareness; nothing to do.

### Feature 001 regression (SC-012)

`tests/phase1/run_harness.sh all` → **OVERALL PASS** (positive T020, negative T021,
identity-unavailable T022, failure-classes all PASS; go2rtc source restored to
`known-person-walk.mp4`). Existing person-detection pipeline unaffected by Phase 1.

### Privacy

- `enrollment-app/data/` holds only runtime state (`app.db` + empty `people/`); nothing
  tracked (`git status` clean of it), nothing committed, no biometric content anywhere.
- No household photos used, moved, or referenced; no Frigate identity touched.

## Phase 2 (People Management) — Gate G2

**Status: PASS — 2026-09-10.** People CRUD, relationship categories, enable/disable,
safe delete with enrolled-state protection, audit events, and the grouped People UI are
implemented and verified. T009–T015 complete.

### T009 — Relationship categories

- `GET /api/relationships` → `{"relationships": ["Family", "Friend", "Neighbor",
  "Other Known"]}` from `app/config.py` (FR-004). Values are user-supplied metadata, never
  inferred from appearance (FR-009).

### T010–T011 — Person CRUD + enable/disable

- `PersonService` (`app/services/person_service.py`) + `app/api/people.py`:
  - `POST /api/people` → 201 detail; display_name required, trimmed, max 100; relationship
    validated against the enum; UUID generated server-side; **never performs any enrollment**.
  - `GET /api/people` → flat `{people:[summary]}` (grouping is a frontend concern per
    contract); `GET /api/people/{id}` → detail incl. `frigate_identity_name` (NULL),
    counts; malformed UUID → 400 VALIDATION_ERROR, unknown → 404 PERSON_NOT_FOUND.
  - `PATCH /api/people/{id}` → `display_name` / `relationship` / `enabled` only;
    `extra="forbid"` rejects immutable fields (`frigate_identity_name`, id); a rename
    never touches the (NULL) Frigate identity name; no-op patches emit no audit noise.
  - Disable preserves the record (distinct from delete); independent of enrollment state.
- Error-envelope fix found by tests: Pydantic v2 embeds the raised exception in
  validation `ctx`, which is not JSON-serializable — the validation handler now sanitizes
  details via `_json_safe` (whitespace-only display_name now returns a clean 400
  VALIDATION_ERROR instead of a 500).

### T012 — Safe delete + enrolled-state protection

- `DELETE /api/people/{id}` → 204; removes the person (photo rows cascade via FK
  `ondelete=CASCADE`; file removal is Phase 3 once uploads exist).
- **Phase-2 deviation (documented in contracts/rest-api.md):** delete is refused with
  `409 ENROLLED_PERSON_DELETE_REFUSED` whenever `enrollment_status == ENROLLED` — even
  with `remove_enrollment=true` — because biometric removal is Phase 6 and refusing is the
  only way to guarantee no orphaned Frigate enrollment (FR-026, user's delete rule #11).
  No person can be ENROLLED in practice yet; the branch is exercised by a direct-DB test.

### T013 — Audit wiring

- Events verified: `PERSON_CREATED`, `PERSON_UPDATED`, `RELATIONSHIP_CHANGED`
  (`details: {from,to}`), `PERSON_ENABLED`, `PERSON_DISABLED`, `PERSON_DELETED`.
- `GET /api/audit?person_id=<uuid>` → newest-first entries with `entity_type`/`entity_id`
  (user-approved deviation from the draft's person_id/photo_id — contract updated),
  `details` JSON only, no biometric content.

### T014 — Frontend (People UI)

- `src/pages/PeoplePage.tsx`: cards grouped under **Family / Friends / Neighbors /
  Other Known**; each card shows initials avatar (no fabricated photos), display name,
  relationship, photo/suitable counts (0 pre-Phase-3), enrollment-status badge, and
  enabled/disabled state. Add Person action, Edit modal (rename, relationship, enabled
  checkbox), Disable/Enable toggle, Delete with a confirmation modal that distinguishes
  **Delete Person** vs. disabling and does not claim Frigate data removal.
- `src/pages/AddPersonPage.tsx`: display name + relationship select (client-side
  validation, backend remains source of truth); photo upload is explicitly announced as
  Phase 3. The disabled "Enrollment not enabled in this phase" control remains.
- `src/api/client.ts` extended with typed people/relationships/audit methods.

### T015 — Tests

`python -m pytest app/tests -q` → **49 passed** (17 Phase 1 + 32 Phase 2). New
`test_people.py` covers: create (valid/trim/whitespace-only/missing name/invalid
relationship/extra-field rejection), list (empty/multiple/values preserved), get
(valid/404/malformed UUID), patch (rename keeps UUID + NULL frigate name, relationship
change, disable/enable, invalid relationship, immutable-field rejection, no-op no-audit),
delete (204/404/enrolled 409), and audit events parametrized across all six actions +
newest-first ordering + from/to details. All names synthetic.

### Networking evidence (SC-011)

- Same-day re-verification: backend `127.0.0.1:8000`, frontend `127.0.0.1:5173`, both
  loopback-only via `lsof`; Vite `/api` proxy exercised live against the running backend.

### Feature 001 regression (SC-012)

`tests/phase1/run_harness.sh all` re-run after Phase 2 → **OVERALL PASS** (all four checks;
go2rtc source restored to `known-person-walk.mp4`). No Ring/HA/Frigate behavior changed by
Phase 2 (people metadata lives entirely in `enrollment-app/data/app.db`).

### Privacy

- No biometric data created (no photo upload yet — Phase 3); no real household identities
  used (synthetic names only, e.g. "Smoke Test Person", deleted after the smoke test).
- Runtime data (`enrollment-app/data/`) remains gitignored; `git status` shows no data
  content. Local runtime DB was reset to a clean state after smoke testing (gitignored
  runtime state only; recreated on next boot).

## Phase 3 (Photo Management) — Gate G3

**Status: PASS — 2026-09-10.** Multi-file upload, private storage, metadata
(Phase 3 fields only), controlled file/thumbnail serving, photo delete, audit events, and
the Person Detail UI are implemented and verified. T016–T021 complete.

### T016 — Upload endpoint

- `POST /api/people/{id}/photos` (multipart field `files`, one or more) → 201
  `{"results": [ {photo_id, original_filename, quality_status, rejection_reason,
  measurements, approved} ]}` — one result per file, partial-failure semantics: a bad file
  is rejected with an explicit reason and never aborts or corrupts the rest of the batch
  (FR-010, US2).
- Ingestion validation only (Phase 3 boundary): size check (`MAX_UPLOAD_BYTES` 20 MB →
  `FILE_TOO_LARGE`), content sniffing by magic bytes (never extension), Pillow decode.
  No face detection, no sharpness/brightness, no duplicates, no enrollment — those are
  Phase 4/5/6. Accepted photos stay `quality_status=PENDING`, `approved=False`,
  `enrolled_in_frigate=False` (FR-019/FR-022).
- **Upload allowlist (user-approved correction): exactly JPEG/PNG/WEBP**, decided by
  decoded/sniffed content — never by filename extension. Valid BMP/GIF/TIFF payloads are
  rejected `UNSUPPORTED_FORMAT` (with `detected_format` in measurements), and extension
  spoofing (e.g. a valid TIFF named `.jpg`) cannot widen the allowlist.
- HEIC/HEIF detected by content (`ftyp` brand) → `UNSUPPORTED_FORMAT` (note: convert to
  JPEG/PNG/WEBP; normalization deferred — no silent conversion) — never silently
  accepted, never a decode failure.
- Format distinctions kept explicit: text renamed `.jpg` → `UNSUPPORTED_FORMAT`;
  corrupt/truncated JPEG magic → `MEDIA_DECODE_FAILURE` (FR-016, never collapsed into a
  generic failure). Extension is never trusted: a valid JPEG named `.txt` is accepted.

### T017 — Metadata extraction

- Pillow records width/height (post-EXIF-transpose), mime by content
  (`image/jpeg|png|webp|...`), and the raw EXIF orientation value in `measurements`
  (`{"orientation": N}`). Originals are stored **byte-for-byte untouched** (FR-011) under
  `people/<uuid>/original/` with randomized UUID filenames — never the user's filename, so
  traversal/duplicate/Unicode names are display metadata only.

### T018 — File + thumbnail endpoints

- `GET .../photos/{photo_id}/file?kind=original|normalized` — `kind=original` serves the
  exact original bytes with its content-derived mime (verified byte-for-byte in tests);
  `kind=normalized` returns an explicit `404 PHOTO_NOT_FOUND` because normalized copies are
  Phase 4 (honest, no fallback); invalid `kind` → 400 VALIDATION_ERROR.
- `GET .../photos/{photo_id}/thumbnail` — generated at upload (max ~300px, JPEG,
  EXIF-transposed, **no face crops**) stored under `people/<uuid>/thumbs/` (private,
  gitignored).
- Cross-person access to any photo endpoint returns 404 (no existence leak); missing
  backing file on disk → safe 404 `PHOTO_NOT_FOUND`, never a 500. Responses never expose
  `storage_path`/`stored_filename` (path-leakage test).

### T019 — Photo delete

- `DELETE .../photos/{photo_id}` → 204; removes the DB row + original/normalized/approved
  copies + thumbnail. Safe for unknown id (404), cross-person id (404), and a vanished
  backing file (still 204, `missing_ok`). Audit `PHOTO_DELETED` (details: person_id only).
- Person delete (Phase 3) now also removes the person's private photo tree (best-effort,
  logged on failure) so no orphaned files are left behind.

### T020 — Frontend

- `src/pages/PersonDetailPage.tsx`: person metadata + `UploadDropzone` (drag-and-drop +
  file picker, multi-file) + `PhotoGrid` (thumbnails, filename, dimensions, size,
  explicit **PENDING** badge, delete with inline confirmation). No quality outcomes are
  fabricated — every uploaded photo visibly remains "stored, not yet analyzed".
- `src/components/UploadDropzone.tsx` shows one result line per file
  (accepted → PENDING badge; rejected → explicit reason).
- `PeoplePage` cards now show "N uploaded photos" (never "suitable" — Phase 4 hasn't run)
  and gain a **Photos** action opening the detail page. `App.tsx` routes
  `people | add | detail`.

### T021 — Tests

`python -m pytest app/tests -q` → **78 passed** (17 Phase 1 + 32 Phase 2 + 29 Phase 3;
+2 for the allowlist tightening).
New `test_photos.py` covers: valid JPEG/PNG/WEBP upload (stored + listed, PENDING,
no paths leaked), corrupt JPEG → MEDIA_DECODE_FAILURE, text-as-jpg → UNSUPPORTED_FORMAT,
HEIC → UNSUPPORTED_FORMAT (convert note), valid-image-wrong-extension accepted,
GIF/BMP/TIFF → UNSUPPORTED_FORMAT (not in allowlist), extension spoofing cannot bypass
the allowlist (valid TIFF named .jpg / GIF named .png rejected),
oversized → FILE_TOO_LARGE (shrunk limit via monkeypatch), mixed batch partial results,
traversal + Unicode + duplicate filenames, cross-person access blocked (get/file/
thumbnail/delete all 404), photo on unknown person 404, file byte-for-byte + mime,
`kind=normalized` 404, invalid kind 400, thumbnail ≤300px, delete removes row + all files,
delete with missing file still 204, unknown photo 404, missing backing file → 404,
person delete removes photo tree, audit PHOTO_UPLOADED/PHOTO_DELETED (metadata-only
details), malformed UUIDs → 400, and no-image-bytes-in-DB invariant.

### Live smoke (real server, loopback)

Single-command flow against `run.sh` on `127.0.0.1:8000`: create person → mixed upload
(1 good JPEG + 1 text file) → results `[PENDING, UNSUPPORTED_FORMAT]` → listing shows only
`good.jpg` → thumbnail served (1767 B, image/jpeg) → file served byte-for-byte
(5426 B, image/jpeg) → photo delete 204 → empty listing → person delete 204. Runtime DB
reset to clean state afterward.

### Feature 001 regression (SC-012)

`tests/phase1/run_harness.sh all` re-run after Phase 3 → **OVERALL PASS** (all four checks;
go2rtc source restored to `known-person-walk.mp4`). Photo ingestion is entirely local to
`enrollment-app/data/` — no Ring/HA/Frigate behavior changed.

### Privacy

- All synthetic media (Pillow-generated) — no household photos anywhere; the existing
  household set at `tests/phase1/test-media/photos/` was not moved or touched.
- Files live only under `enrollment-app/data/people/<uuid>/` (gitignored; verified); no
  image bytes in SQLite; audit details metadata-only; no absolute private paths in any API
  response.

## Phase 4 (Photo Quality Validation) — Gate G4

**Status: PASS — 2026-09-10.** Objective per-photo quality analysis with explicit
classifications is implemented, wired into upload, and verified end-to-end. T022–T028
complete; `pytest` → **98 passed** (78 Phase 1–3 + 20 Phase 4); 001 harness → **OVERALL
PASS** unchanged.

**Phase 3 checkpoint note**: Phase 3 was committed and pushed to `origin/main` as
`9a02e07` ("feat: add private enrollment photo management") after user approval — the
allowlist tightening (exactly JPEG/PNG/WEBP by content, HEIC/GIF/BMP/TIFF →
`UNSUPPORTED_FORMAT`) is part of that commit.

### T022 — Face detector (Frigate-aligned YuNet, no silent fallback)

- **Model**: `facedet.onnx` — YuNet (`cv2.FaceDetectorYN`), the **Frigate-aligned
  `facedet.onnx` used by the validated local Frigate 0.17.2 environment**
  (`frigate/data_processing/real_time/face.py`). No broader compatibility with every
  Frigate installation/version is claimed — only the locally validated 0.17.2 environment.
- **Provenance**: packaged by `NickM-27/facenet-onnx` (Apache-2.0), release v1.0 — the same
  release the validated Frigate 0.17.2 environment downloads
  (`https://github.com/NickM-27/facenet-onnx/releases/download/v1.0/facedet.onnx`).
- **Runtime location**: app-owned private cache `enrollment-app/data/models/facedet.onnx`
  (gitignored). `scripts/fetch_models.sh` copies it from the local Frigate model cache
  (`frigate/config/model_cache/facedet/facedet.onnx`) when present, else downloads from the
  canonical GitHub release; the sha256 is always verified
  (`321aa5a6afabf7ecc46a3d06bfab2b579dc96eb5c3be7edd365fa04502ad9294` — verified on this
  host). The app never depends on the Frigate container being up.
- **App-owned vs borrowed**: app-owned copy in the gitignored runtime cache; the Frigate
  container path is only a preferred copy source for the fetch script.
- **No silent Haar fallback** (user-approved Phase 4 decision): missing/unloadable model →
  `FaceDetectorUnavailableError` (`503 FACE_DETECTOR_UNAVAILABLE` on re-analysis; upload
  degrades to `PENDING` with an explicit `analysis_error`, photo still stored). Verified by
  `test_detector_missing_model_raises_explicit_error_no_fallback`,
  `test_upload_with_missing_model_degrades_cleanly`,
  `test_analyze_missing_model_returns_503`.

### T023–T024 — Face count, size, sharpness, brightness

- `face_count == 0` → `UNSUITABLE`/`NO_FACE`; `> 1` → `REVIEW_REQUIRED`/`MULTIPLE_FACES`
  (hard stop, no auto-select; note: "For enrollment, use an image containing only the
  intended person").
- Face size: `face_size_ratio` (primary-face area / image area) + per-axis ratios;
  `FACE_TOO_SMALL` when below `QualityConfig` baselines (`min_face_area_ratio=0.01`,
  `min_face_width/height_ratio=0.08`).
- Sharpness: variance of Laplacian over the grayscale face crop; `TOO_BLURRY` below
  `min_sharpness_laplacian=40.0`.
- Brightness: mean luminance (0–255) over the face crop; `UNDEREXPOSED` below 40,
  `OVEREXPOSED` above 220. Labeled purely as exposure heuristics — never phrased as
  day/night/indoor (contract).
- **Threshold status**: all values are **INITIAL POC BASELINES — NOT PRODUCTION-TUNED**
  (same stance as feature 001 T033): `min_face_detect_score=0.7`,
  `min_face_area_ratio=0.01`, `min_face_width_ratio=0.08`, `min_face_height_ratio=0.08`,
  `min_sharpness_laplacian=40.0`, `brightness_min=40.0`, `brightness_max=220.0`. Not
  described as proven-optimal; NOT tuned on household media yet (user rule #19).
  Configurable in `QualityConfig`; any future tuning must be audited.
- Orientation: raw EXIF orientation recorded; `exif_transpose` applied to the in-memory
  working copy before measuring; original bytes never modified (verified byte-for-byte).

### T025 — HEIC normalization: DEFERRED (unchanged)

HEIC/HEIF stays `UNSUPPORTED_FORMAT` with the explicit convert note; no silent
normalization; no `normalized/` artifact produced in Phase 4; `kind=normalized` returns an
honest 404. ffmpeg normalization (research.md #6) waits for explicit approval.

### T026 — Analysis pipeline wired into upload + explicit re-analysis

- `PhotoQualityService` (`app/services/quality_service.py`) runs automatically after each
  accepted upload (in-memory EXIF-transposed copy; original untouched): decode → face
  detection → measurements → deterministic classification (contract precedence) → persisted
  metadata. Approval/enrollment fields are never touched by analysis.
- `POST /api/people/{id}/photos/{photo_id}/analyze` provides explicit re-analysis
  (re-reads stored original, overwrites metadata predictably, never approves/enrolls);
  404 for unknown/cross-person ids, 503 when the detector is unavailable.
- Detector unavailable on upload → photo still ingested, `PENDING` +
  `analysis_error: FACE_DETECTOR_UNAVAILABLE` (no fabricated classification).

### T027 — Frontend quality UI

- Photo cards show real results: **✓ Suitable / ✕ Unsuitable / ⚠ Review required /
  Pending** badges + human-readable reason (e.g. "Face too small", "Multiple faces
  detected"), expandable measurements (face count, face size %, sharpness, brightness,
  note), a **Re-analyze** action, and multi-face guidance ("For enrollment, use an image
  containing only the intended person."). No identity/relationship confidence is ever
  shown (none exists). Upload results show the analyzed per-file status.
- `npm run build` clean (tsc + vite).

### T028 — Tests

`python -m pytest app/tests -q` → **98 passed**. New `test_quality.py` (20 tests):
detector loads + finds the fixture face; missing model → explicit error / upload-PENDING /
503 re-analysis, no cached fallback; upload → SUITABLE (measurements sane); NO_FACE;
MULTIPLE_FACES (count 2, guidance note); FACE_TOO_SMALL (detected but below floor);
TOO_BLURRY; UNDEREXPOSED; OVEREXPOSED; suitable never auto-approved/enrolled (DB row +
person record checks); analysis never calls Frigate (no Frigate symbols in the pipeline
modules; flags stay off through re-analysis); re-analysis deterministic;
corrupt-stored-file re-analysis → `MEDIA_DECODE_FAILURE` (never NO_FACE); cross-person
analyze 404; malformed UUID 400; measurements persisted / original byte-for-byte / no
normalized or approved copies; Phase 3 preview + delete still work on analyzed photos;
classification precedence documented.

Fixtures: the single committed public-domain image `astronaut.png` (scikit-image sample
photo of astronaut Eileen Collins, NASA public domain, sha256
`88431cd9…cb5`; see `app/tests/fixtures/README.md`) + derived synthetic images (resize,
composite, blur, brightness) generated at test time. No household/biometric media.

### Live smoke (real server, loopback)

Uploaded the astronaut fixture via the API: result `SUITABLE` (face_count 1, ratio 0.041,
sharpness ~886, brightness ~156); two-face composite → `REVIEW_REQUIRED`/`MULTIPLE_FACES`;
re-analysis returned identical results; original served byte-for-byte. Runtime DB reset to
clean state afterward.

### Feature 001 regression (SC-012)

`tests/phase1/run_harness.sh all` → **OVERALL PASS** (positive, negative,
identity-unavailable, failure-classes all PASS; go2rtc source restored to
`known-person-walk.mp4`). Face analysis is entirely local to `enrollment-app/` — no
Ring/HA/Frigate behavior changed.

### Privacy

- No household images used; no face embeddings generated; no biometric identity created;
  detector output is geometry/quality metadata only; no face crops stored; no raw image
  bytes in DB/logs; no Frigate face-library changes; normalized copies not produced.
- `enrollment-app/data/` (incl. `models/facedet.onnx`) remains gitignored; `git status`
  shows no data content, no runtime images, no `app.db`.

## Gating

**Gate G1 = PASS** (Phase 1 report above).
**Gate G2 = PASS.**
**Gate G3 = PASS** (committed + pushed as `9a02e07`).
**Gate G4 = PASS** (Phase 4 report above). Phase 5 (Approval + Readiness) is actionable
pending the user's review of this report (hard stop per the approved implementation
authorization; nothing committed or pushed for Phase 4).

## Blocking issues

None. Non-blocking observations:
- The pre-existing `*:8000` listener noted in Phase 1 (now gone).
- Pydantic `ctx` serialization fix (T010) is a small but real correctness improvement to
  the error envelope — worth remembering in Phase 3 (same handler serves photo validation
  errors).
- This sandbox reaps background dev servers between shell commands, so the live
  proxy/networking checks were performed within single commands; on a normal Mac the two
  terminal workflow (`run.sh` + `npm run dev`) persists as documented.
- The app-owned detector cache means tests need the model fetched once
  (`scripts/fetch_models.sh`) — detection-dependent tests skip cleanly with an explicit
  message when it is absent, and uploads still work (PENDING + `analysis_error`).