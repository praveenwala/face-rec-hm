# Phase 0 Research: Known Person Enrollment Manager

All items below were candidate `NEEDS CLARIFICATION` points in the Technical Context. Each was
resolved from the user's feature brief, the project constitution
(`.specify/memory/constitution.md`), and verified external facts (Frigate 0.17.2 API docs).
Each entry annotates the constitution principle(s) it satisfies. Items still requiring user
approval are marked **[OPEN DECISION]** and are consolidated in plan.md and the planning
report.

## 1. Application hosting: native vs. container

- **Decision**: For the Mac POC, run the enrollment app **natively** — a Python venv for the
  FastAPI backend and a Vite build/dev server for the React frontend, both bound to
  `127.0.0.1`. Containerization is documented as the production option, not built now.
- **Rationale**: The app owns a private filesystem tree (`enrollment-app/data/`) that must be
  explicitly designed for persistence, permissions, backup, and deletion (production storage
  warning in the brief). A native process makes the data dir a plain host path with no
  container-lifecycle or bind-mount indirection, which is the simplest correct baseline for a
  local-first biometric store. The rest of the repo stays Docker-based (feature 001's
  pipeline is untouched — FR-033).
- **Alternatives considered**: A `docker-compose.yml` service with a bind-mounted `data/` dir
  (rejected for POC: adds image build + lifecycle complexity with no offsetting capability;
  remains a production option); running on the Pi (rejected — constitution I.1/I.2, FR-001).
- **Constitution**: I.1, I.2, II.4, II.5.

## 2. Frontend framework: React (Vite SPA) vs. Next.js

- **Decision**: **React + Vite + TypeScript**, built to static files and served by FastAPI on
  localhost; the Vite dev server proxies `/api` to FastAPI during development.
- **Rationale**: The app is a localhost-only, single-user admin UI. A Vite SPA has no Node
  server component at runtime (fewer moving parts, simpler localhost binding, smaller surface
  to audit for exposure), and the FastAPI backend is the only HTTP listener. Next.js adds a
  Node server and SSR machinery with no benefit for this POC.
- **Alternatives considered**: Next.js standalone (rejected — unnecessary server, more surface
  area); server-rendered Jinja templates (rejected — user explicitly prefers React/Next; a
  typed SPA matches the app's interactive photo-management UI).
- **Constitution**: VI.1 (minimize the stack).
- **Status**: **[OPEN DECISION]** — defaulting to React+Vite; trivially reversible before
  Phase 1.

## 3. Face detection engine for upload quality validation

- **Decision**: Reuse **Frigate's own face-detection model** — `facedet.onnx` (cv2
  FaceDetectorYN / YuNet) — which Frigate 0.17.2 already downloads into its model cache
  (`/config/model_cache/facedet/` inside the container; host path verified at implementation,
  expected `frigate/config/model_cache/facedet/facedet.onnx`, gitignored). OpenCV
  (`opencv-python-headless`) loads it.
- **Rationale**: Validating "suitable" with the exact same detector the runtime uses means a
  photo accepted here is likely to actually produce a usable face when Frigate processes it —
  the objective of the T034 media gate. YuNet is the detector T032/T033 already confirmed in
  the running runtime (`FaceDetectorYN`), so no new model is introduced (constitution VI.2).
- **Fallback**: if the model file is unavailable, fall back to OpenCV's bundled Haar cascade
  with a documented, more conservative face-size default; the validation service never
  invents a model path (constitution IV.2 — explicit failure state).
- **Alternatives considered**: A separate face-detection dependency (e.g. insightface,
  mediapipe) (rejected — new heavy dependency, and may disagree with Frigate's detector,
  making "suitable" diverge from what Frigate accepts); Haar cascade only (rejected as primary
  — weaker small-face detection than YuNet, which is the whole point of the gate).
- **Constitution**: VI.1, VI.2, II.1.
- **Status**: **[OPEN DECISION]** — defaulting to YuNet/facedet.onnx reuse; the fallback is
  documented so no hard dependency is created.

## 4. Face-size, sharpness, and brightness measurement approach

- **Decision**: Measure on the detected face crop: face-size ratio = primary face bounding-box
  area / full-image area (plus per-axis width/height ratios); sharpness = variance of the
  Laplacian over the grayscale face crop; brightness = mean luminance (0–255) of the face
  crop. EXIF orientation is applied via `ImageOps.exif_transpose` before measurement and the
  raw orientation value is recorded.
- **Rationale**: These are standard, cheap, CPU-only measurements consistent with the project's
  "objective measurements vs. heuristics" rule (spec FR-013/FR-014). Thresholds are
  configuration constants with conservative initial defaults, explicitly NOT claimed as tuned
  until validated against real household photos (mirrors feature 001's T033
  `DEFERRED_UNTIL_ENROLLMENT` stance).
- **Alternatives considered**: Learned quality scoring models (rejected — opaque, heavy, and
  unverifiable for this household); manual-only review (rejected — spec US3 requires per-photo
  classifications).
- **Constitution**: II.2 (conservative defaults favoring review/Unknown), V.4.

## 5. Near-duplicate detection (Phase 5)

- **Decision**: Perceptual hashing (`imagehash` pHash, 16×16) stored per photo; photos whose
  hash distance to an existing photo of the same person is below a conservative threshold are
  flagged `REVIEW_REQUIRED` with reason `NEAR_DUPLICATE`.
- **Rationale**: "Obvious duplicates/near-duplicates where practical" (brief). pHash is
  lightweight, deterministic, and stored as metadata (not image content).
- **Alternatives considered**: Exact byte comparison only (rejected — misses re-encoded or
  recompressed copies); embedding-based similarity (rejected — would be identity-adjacent
  inference, which spec FR-013 forbids during quality validation).
- **Constitution**: II.1 (no identity inference during validation), V.4.

## 6. HEIC/HEIF handling

- **Decision**: Detect HEIC/HEIF by content (magic bytes) and extension; normalize via the
  already-installed `ffmpeg` to JPEG into the photo's `normalized/` directory; the original
  file is never modified (spec FR-011/FR-018). If ffmpeg conversion fails or ffmpeg is
  missing, classify `UNSUPPORTED_FORMAT` with an explicit HEIC note.
- **Rationale**: Matches the project's existing media policy exactly — `docs/testing/
  local-mac-testing.md` §10 already documents HEIC → JPEG via ffmpeg and the
  JPEG/PNG canonical formats. Pillow alone cannot decode HEIC reliably without the
  `pillow-heif` dependency; ffmpeg is already a pinned project dependency (feature 001 PD-02).
- **Alternatives considered**: `pillow-heif` (rejected — another native dependency when ffmpeg
  already exists); rejecting HEIC outright (rejected — real household photo sets contain HEIC;
  the brief requires normalization "if supported by the local decoder").
- **Constitution**: VI.1, VI.2.

## 7. Private storage layout and retention

- **Decision**: `enrollment-app/data/` at repo root, gitignored with defense-in-depth:
  `enrollment-app/data/` plus the repo's existing global image/db ignores as backstops. Layout:
  `app.db`, `people/<person-uuid>/{original,normalized,approved}/`. Photos are referenced by
  path in the DB; raw bytes never enter SQLite (spec FR-010).
- **Rationale**: The brief's example layout, plus explicit backup/retention/permissions/deletion
  requirements. The app writes only under `data/`; a `StorageService` centralizes path
  construction with UUID subdirectories and rejects path traversal. Production storage
  requirements (backup strategy, retention policy, permissions, deletion behavior) are
  documented in `docs/production/production-deployment.md` and NOT solved prematurely in the
  POC (brief: "Do not solve production deployment prematurely, but document the requirement").
- **Alternatives considered**: Storing under feature 001's `tests/phase1/test-media/` (rejected
  — that tree is sample media, not app-managed biometric storage); storing in the Frigate
  container volume (rejected — the brief explicitly warns not to copy the container-local
  face-storage architecture).
- **Constitution**: II.4, II.5.

## 8. Frigate 0.17.2 face-library API surface (Phase 6 design basis)

- **Decision**: The Phase 6 service abstraction is designed against the documented Frigate face
  API, and every endpoint name/payload MUST be re-verified against the installed runtime's
  OpenAPI schema (`GET /api/openapi.json` on the running Frigate 0.17.2) as a hard gate task
  (T034) before any integration code runs. Research confirmed these documented endpoints
  (docs.frigate.video/integrations/api + the running-runtime verification requirement):
  - `GET /api/faces` — all registered faces (name → list of image filenames).
  - `POST /api/faces/{name}/create` — create a face name.
  - `POST /api/faces/{name}/register` — register a face image.
  - `POST /api/faces/train/{name}/classify` — classify and save a face training image (the
    official "add training image to a face" endpoint; accepts a training file from the train
    directory or an event_id).
  - `POST /api/faces/{name}/delete` — deregister/delete training files (body `{"ids": [...]}`).
  - `POST /api/faces/reprocess` — reprocess a training image.
  - `POST /api/faces/recognize` — recognize a face from an uploaded image (classification, not
    enrollment; usable later for post-enrollment verification).
  - `GET /api/` ("Frigate is running. Alive and healthy!"), `GET /api/version`,
    `GET /api/stats` — health/version probes.
  - `PUT /api/reindex` — reindex embeddings (verify availability in 0.17.2; used after
    enrollment changes if the runtime requires it).
- **Rationale**: The brief demands "no invented endpoints" and verification against the actual
  installed 0.17.2 API. The docs-derived list above is the design basis; the runtime schema is
  the authority (constitution VI.3 — pin and verify significant dependencies).
- **Alternatives considered**: Using Frigate's internal SQLite/face files directly (rejected —
  violates the abstraction requirement and risks corrupting Frigate's own state); assuming a
  custom enrollment endpoint exists (rejected — no such endpoint exists in 0.17.x).
- **Constitution**: VI.3, IV.2, II.1.
- **Status**: Phase 6 remains **BLOCKED** pending user approval + T034 verification; this
  research entry is design basis only.

## 9. Python toolchain and dependency management

- **Decision**: Python >= 3.11 with `venv` + `pip` + `requirements.txt` (pinned versions),
  pytest for tests. macOS system Python may be older; quickstart documents installing a
  Homebrew Python if needed. No new system-wide tools.
- **Rationale**: FastAPI/Pydantic v2 require modern Python; venv keeps the biometric app's
  dependencies out of the system interpreter. Pinning follows constitution VI.3.
- **Alternatives considered**: `uv` (rejected for now — one more tool to install; easy to adopt
  later, noted as an option); Poetry (rejected — heavier than needed for a POC).
- **Constitution**: VI.1, VI.3.

## 10. Test fixtures and privacy in tests

- **Decision**: Automated tests use **non-household, non-biometric fixtures**: the
  public-domain NASA astronaut portrait shipped with scikit-image (`astronaut`) for
  face-present cases, programmatic composites of it for multi-face cases, synthetic
  blur/noise/brightness variants for quality cases, and corrupt/truncated byte strings for
  decode cases. No household photos ever enter the repo or the test suite.
- **Rationale**: Spec SC-007/SC-010 and constitution II.4/II.5 forbid biometric media in the
  repo; unit-testing the pipeline still needs a detectable face. Public-domain/synthetic
  fixtures satisfy both.
- **Alternatives considered**: Cropping faces from the existing approved sample photos
  (rejected — those are household biometric media, gitignored by design);
  no fixture-based quality tests (rejected — spec US3 requires verifiable classifications).
- **Constitution**: II.4, II.5, V.4.

## 11. Localhost binding and the authentication boundary

- **Decision**: The FastAPI server binds `127.0.0.1` only (never `0.0.0.0`); the frontend is
  served from the same origin in the POC run. The plan records the explicit boundary: any
  future LAN/production access requires authentication (and TLS) before it is permitted; this
  is a documented release criterion, not implemented in the POC (spec FR-002, SC-011).
- **Rationale**: The brief explicitly permits localhost-only for the Mac POC and requires the
  boundary to be documented. Loopback-only binding is enforced in code and asserted by a test.
- **Alternatives considered**: A shared-secret header even on localhost (rejected for POC —
  unnecessary for a single-user loopback app; revisit before any LAN exposure).
- **Constitution**: II.4, II.5.

## 12. Audit logging

- **Decision**: An `audit_log` table records administrative actions (person created/updated/
  deleted, relationship changed, photo uploaded/deleted/approved, enrollment
  requested/completed/removed/failed) with a structured `details` JSON column. Image bytes are
  never logged; secrets never logged (spec FR-031, SC-013).
- **Rationale**: The brief requires auditability for a biometric-management surface; a simple
  append-only table with no PII beyond the person's own identifiers satisfies it for the POC.
- **Alternatives considered**: Structured file logs only (rejected — harder to filter per
  person); full event sourcing (rejected — overkill for this scale).
- **Constitution**: VII.1 (observability), II.4.

## 13. Relationship between this feature and feature 001's T034 gate

- **Decision**: Feature 002 does NOT bypass, modify, or execute 001's T034. The
  `ENROLLMENT_MEDIA_NEEDS_MORE_PHOTOS` gate stays in force and T034 stays `NOT STARTED` until
  (a) this app's photo-management/readiness functionality is validated, or (b) the user
  explicitly decides to use the old manual path. Feature 002's Phase 5 (readiness) validation
  is what produces the evidence for decision (a).
- **Rationale**: The brief is explicit on both points ("Do NOT bypass this gate", "Do not
  silently change feature 001's task status"). The two features remain independent
  specifications; 002 owns the management surface, 001 owns recognition.
- **Alternatives considered**: Having 002 auto-complete 001's T034 (rejected — cross-feature
  task mutation without approval); keeping 002's readiness at a different threshold than 001's
  gate (rejected — 5 suitable photos is the shared requirement).
- **Constitution**: XI.1, XI.2, XI.3.

## Outcome

All Technical Context unknowns are resolved with documented decisions. Three decisions are
marked **[OPEN DECISION]** (hosting mode, frontend framework, face-detection engine) with
recommended defaults that are safe to adopt and reversible before Phase 1 implementation.
No `NEEDS CLARIFICATION` markers remain. Proceeding to Phase 1 design.