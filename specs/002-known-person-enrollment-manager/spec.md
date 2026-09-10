# Feature Specification: Known Person Enrollment Manager

**Feature Branch**: `002-known-person-enrollment-manager`
**Created**: 2026-09-10
**Status**: Draft
**Input**: User description — "Build a LOCAL web application for managing known people and their
approved face-enrollment photos, replacing the manual photo workflow currently blocking
feature 001's T034, without changing the recognition pipeline or enrolling anyone yet."

## Clarifications

### Session 2026-09-10 (rulings carried from the user's feature brief — authoritative)

- Identity and relationship are separate concepts. Frigate answers "who does this face match?"
  (`identity`); this application answers "what manually assigned relationship does this known
  person have?" (`relationship`). Relationship is NEVER inferred from appearance.
- ONE people model/table. Family/Friend/Neighbor/Other Known are metadata values on a person,
  used only to visually group the UI — never separate identity databases.
- Person identifiers are UUIDs, never display names. Display names are editable metadata;
  renaming a person must not silently create or break a biometric identity.
- Uploading a photo MUST NOT enroll it. Enrollment is a separate, explicit user action
  ("Enroll Approved Photos") — NO SILENT BIOMETRIC ENROLLMENT.
- A person reaches `READY` only with >= 5 suitable, approved photos. `READY` never
  automatically means `ENROLLED`.
- Multi-face enrollment photos are not silently accepted: exactly one usable face is
  preferred; multiple faces → `REVIEW_REQUIRED`/`UNSUITABLE` (no automatic face selection in
  the MVP).
- Unknown visitors never automatically become Person records. Unknown remains an event/state;
  enrolling someone is always a separate manual workflow.
- Disable ≠ Delete. Disable preserves the record and stops recognition mapping where
  supported; Delete removes the record, its private photo storage, and (once integrated) the
  Frigate enrollment.
- The app binds localhost only for the Mac POC. No LAN/Internet exposure; authentication
  becomes mandatory before any non-localhost access.
- Existing feature 001 pipeline, Frigate person-detection config, and Ring/HA automations are
  untouched by this feature. Feature 001's T034 stays NOT STARTED until the user decides how
  the enrollment path (this app vs. the old manual path) resolves it.

## User Scenarios & Testing

### User Story 1 - Create a Known Person (Priority: P1)

As a homeowner, I can create a known person and manually assign their relationship, so that
my known-person library starts from explicit user intent rather than from observation.

**Why this priority**: No other story exists without a person record to attach it to.

**Independent Test**: Create a person with a display name and a relationship category and
verify the record appears in the library with no biometric data created anywhere.

**Acceptance Scenarios**:

1. **Given** the local application is running, **When** I create a person with a display name and
   a relationship category, **Then** the person appears in the library and no enrollment or
   biometric data is created by that action.
2. **Given** a person record exists, **When** I view it, **Then** I see its display name,
   relationship, photo count, and enrollment status.
3. **Given** I attempt to create a person without a display name or relationship, **When** I submit,
   **Then** the application rejects it with a clear validation error.

---

### User Story 2 - Upload Enrollment Photos (Priority: P1)

As a homeowner, I can upload multiple private photos for a known person, so that a candidate
photo set is collected on my own local storage.

**Why this priority**: Photo collection is the prerequisite for every later validation and
enrollment story.

**Independent Test**: Upload several photos for one person via the file picker (and, where
practical, drag-and-drop) and verify each is stored privately and listed under that person.

**Acceptance Scenarios**:

1. **Given** a person exists, **When** I upload one or more photos in one action, **Then** each
   file is stored under that person's private storage and appears in the photo list.
2. **Given** I upload a file, **When** it is processed, **Then** the original file is never
   silently overwritten or altered.
3. **Given** I upload an unsupported or undecodable file, **When** it is processed, **Then** the
   file   receives an explicit failure classification (e.g. `UNSUPPORTED_FORMAT` or
   `MEDIA_DECODE_FAILURE`) rather than a generic "upload failed".
4. **Given** a photo exists, **When** I delete it, **Then** the photo metadata and its stored
   files are removed.

---

### User Story 3 - Validate Photo Quality (Priority: P1)

As a homeowner, I can see which photos are suitable for face enrollment and why others were
rejected, so that I do not waste an enrollment attempt on unusable images.

**Why this priority**: Enrollment quality is the gate to recognition accuracy (feature 001's
feature 001's T034 media gate demonstrated this need).

**Independent Test**: Upload a mix of suitable, blurry, tiny-face, no-face, and multi-face
images and verify each receives the correct explicit classification with reasons.

**Acceptance Scenarios**:

1. **Given** a photo has exactly one clearly detectable face, **When** it is analyzed, **Then** it
   is classified `SUITABLE` with its measured properties recorded.
2. **Given** a photo has no detectable face, **When** it is analyzed, **Then** it is classified
   `UNSUITABLE` with reason `NO_FACE`.
3. **Given** a photo has a face that is too small, blurry, or badly exposed, **When** it is
   analyzed, **Then** it is classified `UNSUITABLE` with the specific reason
   (`FACE_TOO_SMALL`, `TOO_BLURRY`, `UNDEREXPOSED`, or `OVEREXPOSED`).
4. **Given** a photo has more than one face, **When** it is analyzed, **Then** it is marked
   `REVIEW_REQUIRED` with reason `MULTIPLE_FACES` and is never silently accepted with one
   face auto-selected.
5. **Given** a file cannot be decoded, **When** it is analyzed, **Then** it is classified with a
   decode/format failure reason, never collapsed into `NO_FACE`.
6. **Given** quality classifications are displayed, **When** I inspect them, **Then** objective
   measurements (dimensions, face count, face size ratio, sharpness, brightness) are shown
   separately from derived judgments, and no unmeasurable claims (e.g. "definitely daylight")
   are made.

---

### User Story 4 - Enrollment Readiness (Priority: P1)

As a homeowner, I can see whether a person has enough suitable photos before enrollment, so
that I enroll only when the photo set is adequate.

**Why this priority**: This is the gate that feature 001's T034 is currently blocked on.

**Independent Test**: Give a person fewer than 5 suitable approved photos and confirm
`NOT_READY`; add photos until >= 5 and confirm `READY`; confirm readiness never triggers an
enrollment by itself.

**Acceptance Scenarios**:

1. **Given** a person has fewer than 5 suitable approved photos, **When** readiness is checked,
   **Then** the status is `NOT_READY` with a count like "3 / 5 suitable photos" and a list of
   what is missing.
2. **Given** a person has at least 5 suitable approved photos, **When** readiness is checked,
   **Then** the status is `READY`.
3. **Given** photos that are `UNSUITABLE`, `REVIEW_REQUIRED`, or not yet approved, **When**
   readiness is computed, **Then** they are not counted toward the 5.
4. **Given** a person becomes `READY`, **When** no further action is taken, **Then** the person
   remains `READY` and is never automatically enrolled.

---

### User Story 5 - Manage Known People (Priority: P2)

As a homeowner, I can edit, disable, or delete known people, so that the library stays
accurate and under household control.

**Why this priority**: Management is needed for long-term accuracy but not to prove the MVP.

**Independent Test**: Edit a person's display name and relationship, disable the person (record
preserved), then delete the person and confirm the record and its private photos are gone.

**Acceptance Scenarios**:

1. **Given** a person exists, **When** I edit their display name, **Then** the change is saved and
   does not alter any enrolled identity name (rename never silently re-enrolls).
2. **Given** a person exists, **When** I disable them, **Then** the record is preserved and marked
   disabled; this is distinct from deletion and from enrollment removal.
3. **Given** a person exists, **When** I delete them with explicit confirmation, **Then** the
   person record, their photo metadata, and their private photo files are removed.
4. **Given** a person has an active Frigate enrollment, **When** I attempt to delete them,
   **Then** the application refuses until the enrollment is explicitly removed (or requires an
   explicit remove-enrollment confirmation), so no orphaned biometric enrollment is left
   behind.

---

### User Story 6 - Group People by Relationship (Priority: P2)

As a homeowner, I can view known people grouped into Family, Friends, Neighbors, and Other
Known, so that the library is scannable at a glance.

**Why this priority**: Cheap UI grouping that depends only on US1 data.

**Independent Test**: Create people in each category and verify the People page groups them
under the correct headings.

**Acceptance Scenarios**:

1. **Given** people exist in multiple relationship categories, **When** I open the People page,
   **Then** each person appears under exactly one category heading.
2. **Given** a person's relationship changes, **When** I return to the People page, **Then** the
   person appears under the new heading.
3. **Given** the category list is extended later, **When** a new category is added to the
   configuration, **Then** no recognition architecture changes are required (categories are
   metadata, not identities).

---

### User Story 7 - Enroll Approved Photos into Frigate (Priority: P1/P2)

As a homeowner, I can explicitly enroll a person's approved photos into Frigate once the
person passes the readiness gate, so that the identity becomes available for recognition.

**Why this priority**: This is the story that connects the library to recognition — it is
planned and designed now but **MUST NOT be executed until explicitly approved** (see
Dependencies).

**Independent Test**: With the readiness gate satisfied, press "Enroll Approved Photos" and
verify the identity appears in Frigate's face library with the approved images, and that
nothing enrolled before the explicit action.

**Acceptance Scenarios**:

1. **Given** a person is `READY`, **When** I explicitly trigger enrollment, **Then** the approved
   photos are submitted to Frigate, the person's status becomes `ENROLLED`, and the enrolled
   identity name is recorded.
2. **Given** a person is not `READY`, **When** I attempt enrollment, **Then** the application
   refuses with a readiness error.
3. **Given** an enrollment attempt fails (Frigate unavailable, API error), **When** it completes,
   **Then** the person's status becomes `ERROR` with the specific failure reason, and no
   partial biometric state is silently left behind.
4. **Given** two persons try to enroll the same identity name, **When** the second enrollment is
   attempted, **Then** it is rejected with an `IDENTITY_CONFLICT` error and requires
   disambiguation.

---

### User Story 8 - Remove Enrollment (Priority: P2)

As a homeowner, I can explicitly remove a person's biometric enrollment and associated
private data, so that recognition stops cleanly and no biometric residue remains.

**Why this priority**: Required for household control once enrollment exists.

**Independent Test**: Remove an enrolled person's enrollment and verify the identity is gone
from Frigate's face library and the person returns to a non-enrolled state.

**Acceptance Scenarios**:

1. **Given** a person is `ENROLLED`, **When** I explicitly remove their enrollment, **Then** the
   identity is removed from Frigate and the person's status returns to non-enrolled.
2. **Given** an enrollment is removed, **When** the person appears at the camera again, **Then**
   feature 001's pipeline no longer reports that identity (recognition behavior is Frigate's,
   driven by the library state this application manages).
3. **Given** a person is `ENROLLED`, **When** I delete the person with the remove-enrollment
   option, **Then** the enrollment, the record, and the private photos are all removed — no
   orphaned biometric enrollment remains.

## Edge Cases

- A photo has zero faces (covered: `NO_FACE`).
- A photo has two or more faces (covered: `MULTIPLE_FACES` → `REVIEW_REQUIRED`, never silent
  single-face selection).
- A face is very small relative to the frame (covered: `FACE_TOO_SMALL`; threshold
  configurable, initial values documented as un-tuned).
- A face is blurred, very dark, or overexposed (covered: `TOO_BLURRY`, `UNDEREXPOSED`,
  `OVEREXPOSED`).
- A file decodes fine but contains no recognizable face (must never be reported as
  `MEDIA_DECODE_FAILURE`; and vice versa).
- HEIC/HEIF input: detected, normalized to JPEG when the local decoder (ffmpeg) supports it,
  otherwise a clear `UNSUPPORTED_FORMAT` error. The original is never overwritten.
- A corrupt or truncated image (covered: `MEDIA_DECODE_FAILURE`, distinct from `NO_FACE`).
- Two uploaded photos are obvious duplicates/near-duplicates (covered in Phase 5 where
  practical via perceptual hashing; flagged `REVIEW_REQUIRED`).
- The same display name is used for two people (allowed as metadata, but the enrolled
  identity name must remain unique — `IDENTITY_CONFLICT`).
- A display name is renamed after enrollment (identity name unchanged; no re-enrollment).
- A person is disabled while enrolled (record preserved; recognition mapping stops per future
  HA design; enrollment data retained until explicitly removed).
- A person is deleted while enrolled (refused unless enrollment removal is explicitly
  included — no orphaned biometric enrollment).
- Frigate is offline during enrollment (explicit `FRIGATE_UNAVAILABLE`, person → `ERROR`).
- Frigate's face library and the application disagree on which identities exist (Phase 6
  reconciliation surfaces the difference; the app never silently deletes or creates Frigate
  identities).
- The same photo file is uploaded twice (near-duplicate detection where practical).
- An upload arrives with a very large file (explicit size limit rejection).
- Unknown visitors detected by feature 001 must never appear as Person records here (no import
  path from recognition events exists or is planned in this feature).
- The database or storage layer fails (explicit `DATABASE_FAILURE` / `STORAGE_FAILURE`
  classifications, never a generic "upload failed").
- The app is started on a host without the expected Python/Node toolchain (quickstart covers
  prerequisites; failures are explicit).

## Requirements

### Functional Requirements

- **FR-001**: The application MUST run locally on the AI/compute host (the Mac for the POC)
  and MUST NOT run on the Raspberry Pi 3.
- **FR-002**: The application MUST be reachable only on localhost (loopback) during the Mac
  POC; authentication MUST become mandatory before any non-localhost access.
- **FR-003**: The application MUST support creating a known person with a display name and a
  manually assigned relationship category.
- **FR-004**: The initial relationship categories MUST be exactly Family, Friend, Neighbor,
  and Other Known, defined as a configurable list so categories can be added later without
  changing recognition architecture.
- **FR-005**: Relationship MUST always be user-supplied; the application MUST NOT infer
  relationship, gender, age, ethnicity, or other sensitive attributes from face appearance.
- **FR-006**: The application MUST use a stable internal UUID as the person identifier; display
  names MUST NOT be used as filesystem or identity identifiers.
- **FR-007**: Display names MUST be editable metadata; renaming a person MUST NOT change or
  recreate any biometric identity.
- **FR-008**: The application MUST store a separate `frigate_identity_name` per person once
  enrolled, distinct from the display name, and MUST prevent duplicate enrolled identity names
  (`IDENTITY_CONFLICT`).
- **FR-009**: The application MUST support uploading multiple photos per person in a single
  action (multi-file upload), with drag-and-drop where practical.
- **FR-010**: Photo bytes MUST be stored in a private local filesystem under
  `enrollment-app/data/`, gitignored; raw image bytes MUST NOT be stored in the database.
- **FR-011**: The original uploaded file MUST be preserved unmodified; any normalization (e.g.
  HEIC→JPEG) MUST produce a separate file and never silently overwrite the original.
- **FR-012**: The application MUST validate each uploaded photo: decode, dimensions, face
  count, primary face presence, face size in frame, sharpness, brightness/exposure, and
  orientation where measurable.
- **FR-013**: Quality validation MUST NOT perform identity inference — it must never compare an
  uploaded face against enrolled identities.
- **FR-014**: Quality validation MUST distinguish objective measurements from derived
  judgments and MUST NOT claim unmeasurable semantic qualities (e.g. "this is daylight").
- **FR-015**: Each photo MUST have an explicit quality status from
  `PENDING | SUITABLE | UNSUITABLE | REVIEW_REQUIRED`.
- **FR-016**: Rejection MUST carry an explicit reason code: `NO_FACE`, `MULTIPLE_FACES`,
  `FACE_TOO_SMALL`, `TOO_BLURRY`, `UNDEREXPOSED`, `OVEREXPOSED`, `MEDIA_DECODE_FAILURE`,
  `UNSUPPORTED_FORMAT` (plus `NEAR_DUPLICATE` where near-duplicate detection is implemented).
  `MEDIA_DECODE_FAILURE`/`UNSUPPORTED_FORMAT` MUST NOT be collapsed into `NO_FACE`.
- **FR-017**: Photos with more than one face MUST be marked `REVIEW_REQUIRED` (reason
  `MULTIPLE_FACES`) and MUST NOT be silently accepted with an automatically chosen face.
- **FR-018**: The application MUST support JPEG, PNG, and WEBP at minimum, and any other format
  the installed image stack can decode; HEIC/HEIF MUST be detected and normalized to JPEG when
  the local decoder supports it, otherwise rejected with `UNSUPPORTED_FORMAT`.
- **FR-019**: Photo approval MUST be an explicit user action separate from upload; uploading a
  photo MUST NOT mark it approved.
- **FR-020**: The application MUST compute enrollment readiness as the count of suitable AND
  approved photos, with a required minimum of 5.
- **FR-021**: Fewer than 5 suitable approved photos MUST result in `NOT_READY`; at least 5 MUST
  result in `READY`.
- **FR-022**: `READY` MUST NOT automatically enroll; enrollment MUST be a separate explicit
  user action ("Enroll Approved Photos").
- **FR-023**: The application MUST distinguish photo approval from person enrollment in both
  data and UI.
- **FR-024**: Person enrollment status MUST use explicit states:
  `DRAFT | NOT_READY | READY | ENROLLING | ENROLLED | ERROR`, with `DISABLED` expressed via an
  independent enabled flag on the person.
- **FR-025**: Disable MUST preserve the person record and stop recognition mapping where
  supported; Delete MUST remove the person, their photos, and (once integrated) their Frigate
  enrollment, with explicit confirmation.
- **FR-026**: Deleting a person with an active Frigate enrollment MUST require explicit
  removal of that enrollment (or an explicit remove-enrollment confirmation) — no orphaned
  biometric enrollment.
- **FR-027**: Unknown visitors MUST NOT automatically become Person records; no import path
  from recognition events is provided by this feature.
- **FR-028**: All Frigate interaction MUST be isolated behind a service abstraction; raw
  Frigate HTTP calls MUST NOT appear in controllers or UI code.
- **FR-029**: Frigate behavior MUST be based on the actual Frigate 0.17.2 API verified from
  the installed runtime; no invented endpoints.
- **FR-030**: Enrollment into Frigate MUST NOT be executed in this feature until explicitly
  approved; the feature's plan MUST keep that phase blocked.
- **FR-031**: The application MUST record local administrative actions in an audit log (person
  created/edited/deleted, relationship changed, photo uploaded/deleted/approved/rejected,
  enrollment requested/completed/removed/failed) without logging image content or secrets.
- **FR-032**: Upload, storage, database, and Frigate failures MUST use explicit error
  classifications (`MEDIA_DECODE_FAILURE`, `NO_FACE_DETECTED`, `MULTIPLE_FACES`,
  `FACE_TOO_SMALL`, `QUALITY_REJECTED`, `STORAGE_FAILURE`, `DATABASE_FAILURE`,
  `FRIGATE_UNAVAILABLE`, `FRIGATE_ENROLLMENT_FAILURE`, `IDENTITY_CONFLICT`) and MUST NOT be
  collapsed into a generic failure.
- **FR-033**: The application MUST NOT modify feature 001's Frigate person-detection config,
  MQTT wiring, or Ring/HA automations.

### Key Entities

- **Person**: A known person intentionally added by the homeowner. Holds display name,
  `frigate_identity_name` (once enrolled), relationship category, enabled flag, and enrollment
  status.
- **EnrollmentPhoto**: One uploaded candidate photo for a person. Holds original filename,
  stored paths, mime type, dimensions, file size, measured quality properties, quality status,
  rejection reason, approval flag, and enrollment flag. Bytes live on disk, never in the DB.
- **Relationship Category**: User-maintained metadata on a person. Initial values: Family,
  Friend, Neighbor, Other Known. Configurable list; never inferred from appearance.
- **Readiness**: The derived "enough suitable approved photos" state for a person (>= 5).
- **Audit Log Entry**: A local record of an administrative action for accountability.
- **Frigate Identity**: The recognition-side entity owned by Frigate (its face library),
  referenced by the person's `frigate_identity_name`; this feature manages the mapping to it,
  never recognition behavior itself.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Creating a person performs zero biometric enrollment actions (verified: no
  Frigate API calls, no face-library writes, no biometric artifact creation).
- **SC-002**: In a test set of 20 uploaded photos covering suitable, no-face, tiny-face,
  blurry, under/overexposed, multi-face, and corrupt files, every photo receives the correct
  explicit classification with reason — 100% of files get a classification; no file is
  reported as a generic "upload failed".
- **SC-003**: 100% of multi-face uploads in the test set are marked `REVIEW_REQUIRED`/not
  silently accepted.
- **SC-004**: A person with 3 suitable approved photos shows `NOT_READY`; after reaching 5
  suitable approved photos the same person shows `READY` — verified in at least 3 test
  persons.
- **SC-005**: `UNSUITABLE`, `REVIEW_REQUIRED`, and not-yet-approved photos never count toward
  the readiness minimum in any test scenario.
- **SC-006**: Reaching `READY` never triggers an enrollment: verified that no enrollment
  action occurs unless the user explicitly triggers it.
- **SC-007**: All uploaded test files live under `enrollment-app/data/` and `git status`
  shows no biometric files tracked; `git check-ignore` confirms the data path.
- **SC-008**: Deleting a person removes the person record, all photo metadata rows, and all
  stored photo files for that person; deleting an enrolled person is refused (or requires
  explicit enrollment removal) and never leaves an orphaned Frigate enrollment.
- **SC-009**: A display-name rename leaves `frigate_identity_name` unchanged (no re-enrollment,
  no identity conflict) in all rename tests.
- **SC-010**: Unknown faces never appear as Person records: no automated path exists from
  recognition events into the people library.
- **SC-011**: The application is reachable only on 127.0.0.1 during the POC; no listener on
  other interfaces is present in test.
- **SC-012**: With feature 001's harness (`tests/phase1/run_harness.sh all`) run before and
  after the enrollment app's phases 1–5, the harness result is unchanged (existing
  person-detection pipeline unaffected).
- **SC-013**: Audit log entries exist for person create/edit/delete, relationship change,
  photo upload/delete/approve, and (once executed) enrollment request/completion/removal, with
  no image bytes and no secrets in any entry.
- **SC-014**: Frigate integration (Phase 6) is not executed: the task list keeps enrollment
  tasks blocked, and no Frigate identity is created by any test in phases 1–5.

## Assumptions

- The app runs on the same local compute host as the POC (the Intel Mac); a dedicated
  production host is a later decision and must preserve the local-first design.
- Mac POC hosting is a native Python/Node process (venv + Vite build) rather than a container;
  containerization remains an option for production and does not change the data model. [Open
  decision — see plan.md]
- Frontend is a React (Vite) single-page application served from the FastAPI backend on
  localhost; Next.js was considered and deferred as unnecessary server weight for a local POC.
  [Open decision — see plan.md]
- Quality thresholds (face-size ratio, sharpness variance, brightness range) start at
  documented conservative defaults and are explicitly NOT claimed as tuned until validated
  against real household photos — mirroring feature 001's T033 deferral stance.
- Face detection reuses the same YuNet ONNX model Frigate 0.17.2 itself uses
  (`facedet.onnx`) so "suitable" aligns with what Frigate will actually process; the exact
  model file path on the host is verified at implementation. [Open decision — see plan.md]
- Test fixtures use public-domain/synthetic images (e.g. the scikit-image astronaut portrait
  and programmatic composites), never household biometric media.
- Python >= 3.11 and a current Node LTS are available on the Mac; if the system Python is
  older, a Homebrew Python is installed (documented in quickstart).
- The enrollment app does not read or write feature 001's config, MQTT topics, or
  `tests/phase1/test-media/photos` — existing photos are not moved; the user re-uploads them
  through the app when they choose.
- T034 (feature 001) remains NOT STARTED and the existing enrollment-media gate
  (`ENROLLMENT_MEDIA_NEEDS_MORE_PHOTOS`) remains in force until the user decides whether this
  app or the old manual path resolves it.

## Dependencies

- The project constitution (`.specify/memory/constitution.md`) remains authoritative for
  privacy, local-first processing, explicit enrollment, and change control.
- A running local Frigate 0.17.2 instance is available for Phase 6 (enrollment) work only;
  its API must be verified from the installed runtime before any integration task runs.
- Python >= 3.11 and Node.js LTS with npm are available on the Mac; ffmpeg is available for
  HEIC normalization (already a project dependency per feature 001's PD-02).
- **Phase 6 (Frigate enrollment) MUST NOT begin without explicit user approval**; the
  corresponding tasks are blocked in the plan. Home Assistant integration (Phase 7) is
  designed for but NOT implemented by this feature.