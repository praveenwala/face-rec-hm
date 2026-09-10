# Data Model: Known Person Enrollment Manager

Derived from the spec's Key Entities and the user's feature brief. This is a **physical
database model** for feature 002's own SQLite database (`enrollment-app/data/app.db`) — the
first database in this repo. It is deliberately separate from feature 001's data model
(Frigate events, Recognition Results, Notification Events), which stays untouched: feature 002
manages the *people/photo/approval* surface; Frigate continues to own recognition behavior.

## Design invariants (from the brief, non-negotiable)

- One people model/table. Relationship categories are metadata values, never separate
  databases.
- Person identifiers are UUIDs, never display names. Display names are editable metadata.
- `display_name`, `frigate_identity_name`, and the Frigate library identity are three distinct
  things (see "Identity mapping" below).
- Raw image bytes never enter SQLite — only paths into the private filesystem.
- Photo approval and person enrollment are distinct state machines.
- Unknown visitors never become Person rows (there is no import path from recognition events).

## Identity mapping (source-of-truth split)

| Concept | Owner | Notes |
|---|---|---|
| `Person.id` (UUID) | This application | Stable internal identifier; used for storage paths and all API references |
| `Person.display_name` | This application | Editable metadata; never an identifier |
| `Person.frigate_identity_name` | Set by this app at enrollment; stored on the person | The name that exists in Frigate's face library; unique among enrolled persons (`IDENTITY_CONFLICT` enforced against both the local table and Frigate's `/api/faces`) |
| Recognition output (`sub_label`) | Frigate | Frigate reports `frigate_identity_name`; it knows nothing about `display_name` or relationship |

**Rename safety**: changing `display_name` updates only that column. `frigate_identity_name`
is set once at enrollment (defaulting to a suggested value derived from the display name, but
user-editable at enrollment time) and never changes on rename. Frigate's library entry is
touched only by explicit enrollment/removal actions (Phase 6).

## Entities

### Person

| Field | Type | Notes |
|---|---|---|
| `id` | string (UUID v4) | Primary key; storage directory name |
| `display_name` | string, required | Editable; max length enforced (e.g. 100 chars) |
| `frigate_identity_name` | string \| null | Set at enrollment (Phase 6); unique when non-null (enforced app-side + verified against Frigate) |
| `relationship` | enum: `Family \| Friend \| Neighbor \| Other Known` | Required at creation; editable; sourced from a configurable category list (spec FR-003/FR-004/FR-005) |
| `enabled` | boolean, default `true` | Independent of enrollment status. `false` = disabled: record preserved, recognition mapping stops per future HA design (spec FR-025) |
| `enrollment_status` | enum: `DRAFT \| NOT_READY \| READY \| ENROLLING \| ENROLLED \| ERROR` | Derived from photos (DRAFT/NOT_READY/READY) or set by the enrollment service (ENROLLING/ENROLLED/ERROR) — see state transitions |
| `representative_photo_id` | FK → EnrollmentPhoto \| null | Photo used on the person card; set to the first approved suitable photo (fallback: first photo) |
| `created_at` / `updated_at` | datetime | `updated_at` changes on any field change |

**Validation rules**:
- Created only by explicit user action with display name + relationship (spec US1).
- `relationship` is never inferred from appearance (FR-005).
- Deleting a person with `enrollment_status = ENROLLED` is refused unless the caller requests
  explicit enrollment removal (FR-026) — enforced in the service layer, not just the UI.
- `enrollment_status` and `enabled` are independent: a disabled person can be ENROLLED; an
  enabled person can be DRAFT.

### EnrollmentPhoto

| Field | Type | Notes |
|---|---|---|
| `id` | string (UUID v4) | Primary key |
| `person_id` | FK → Person | Cascade-deleted with the person |
| `original_filename` | string | User's original filename (display only; not a storage identifier) |
| `stored_filename` | string | Randomized storage filename (UUID-based) |
| `storage_path` | string | Path relative to `enrollment-app/data/`, e.g. `people/<uuid>/original/<file>` |
| `mime_type` | string | Detected by content, not extension |
| `width` / `height` | int | Post-orientation-fix dimensions |
| `file_size` | int | Bytes |
| `orientation` | int \| null | EXIF orientation value before transpose; recorded, not a rejection reason |
| `face_count` | int | Detected faces above the face-detection threshold |
| `face_size_ratio` | float \| null | Primary face box area / image area (plus per-axis ratios in `measurements`) |
| `sharpness` | float \| null | Laplacian variance over the face crop |
| `brightness` | float \| null | Mean luminance (0–255) over the face crop |
| `quality_status` | enum: `PENDING \| SUITABLE \| UNSUITABLE \| REVIEW_REQUIRED` | Computed at upload; `PENDING` only during processing |
| `rejection_reason` | enum \| null | `NO_FACE \| MULTIPLE_FACES \| FACE_TOO_SMALL \| TOO_BLURRY \| UNDEREXPOSED \| OVEREXPOSED \| MEDIA_DECODE_FAILURE \| UNSUPPORTED_FORMAT` — never a redundancy advisory (`NEAR_DUPLICATE` is advisory metadata, not a rejection) |
| `rejection_details` | JSON \| null | Supplementary measurement values + any secondary reason codes (never image content) |
| `measurements` | JSON \| null | Full objective measurement record (dims, ratios, Laplacian, luminance, pHash) — kept separate from derived status |
| `approved` | boolean, default `false` | Explicit user approval (spec FR-019); approving is never automatic; only `SUITABLE` photos may be approved; reanalysis that degrades an approved photo auto-clears it |
| `enrolled_in_frigate` | boolean, default `false` | Set true by Phase 6 enrollment for each submitted photo |
| `duplicate_group` | string \| null | Exact-duplicate bucket: SHA-256 of the stored original file, assigned at upload. Only one member of a group counts toward readiness. Legacy null rows each count as unique |
| `created_at` | datetime | |

**Storage layout** (per person UUID, under `enrollment-app/data/people/`):

```text
people/<person-uuid>/
├── original/     # byte-for-byte copy of the uploaded file (never modified)
├── normalized/   # canonical JPEG/PNG (HEIC→JPEG etc.) — the enrollment candidate
└── approved/     # (Phase 6) copies submitted to Frigate, kept for audit/re-submission
```

**Validation rules**:
- Uploading a photo never sets `approved` (FR-019) and never enrolls (FR-022).
- `quality_status = SUITABLE` requires exactly one detected face above threshold AND
  face-size/sharpness/brightness checks passing (FR-012–FR-017).
- `face_count > 1` → `REVIEW_REQUIRED` + `MULTIPLE_FACES`; never silent single-face selection
  (FR-017).
- Decode/format failures are distinct from `NO_FACE` (FR-016).
- Deleting a photo removes its DB row and its files under `original/`, `normalized/`, and
  `approved/` (spec US2 scenario 4).

### AuditLogEntry

| Field | Type | Notes |
|---|---|---|
| `id` | int | Auto-increment PK |
| `timestamp` | datetime | UTC |
| `action` | enum | `PERSON_CREATED \| PERSON_UPDATED \| RELATIONSHIP_CHANGED \| PERSON_DISABLED \| PERSON_ENABLED \| PERSON_DELETED \| PHOTO_UPLOADED \| PHOTO_DELETED \| PHOTO_APPROVED \| PHOTO_UNAPPROVED \| READINESS_CHANGED \| ENROLLMENT_REQUESTED \| ENROLLMENT_COMPLETED \| ENROLLMENT_REMOVED \| ENROLLMENT_FAILED \| RECONCILIATION_RUN` |
| `entity_type` | string \| null | Subject kind: `person` \| `photo` \| `system` (user-approved implementation instruction — replaces person_id/photo_id with a general subject reference) |
| `entity_id` | string \| null | UUID of the subject entity |
| `details` | JSON \| null | Structured context (e.g. old/new relationship values, reason codes). Never image bytes; never secrets (spec FR-031) |

### RelationshipCategory

Not a table — a **configurable list** (e.g. `RELATIONSHIPS = ["Family", "Friend",
"Neighbor", "Other Known"]`) exposed via `GET /api/relationships` and used for Person
validation and UI grouping. Adding a category later is a config change, never a schema or
recognition change (spec FR-004, US6 scenario 3).

## Quality status model

```text
upload received
  └─> PENDING (processing)
        ├─> decode/format failure        → UNSUITABLE  (MEDIA_DECODE_FAILURE | UNSUPPORTED_FORMAT)
        ├─> face_count == 0              → UNSUITABLE  (NO_FACE)
        ├─> face_count > 1               → REVIEW_REQUIRED (MULTIPLE_FACES)
        ├─> face too small               → UNSUITABLE  (FACE_TOO_SMALL)
        ├─> too blurry / under/overexposed → UNSUITABLE (TOO_BLURRY | UNDEREXPOSED | OVEREXPOSED)
        ├─> near-duplicate of existing   → ADVISORY ONLY: stays SUITABLE, records
        │                                  near_duplicate_advisory metadata [Phase 5]
        └─> all checks pass              → SUITABLE
```

`REVIEW_REQUIRED` photos are shown to the user with the reason; the user may delete them or
provide a cleaner image. In the MVP there is no path to force-approve a multi-face photo
(face cropping is a documented future feature).

**Phase 5 duplicate semantics** (user-approved Phase 5 rules; `contracts/photo-quality.md`):

- **Exact duplicates** (byte-identical SHA-256) share a `duplicate_group`; only one member of
  an exact-duplicate group may contribute a readiness credit. Uploading the same photo five
  times can never produce READY.
- **Near-duplicates** (perceptual hash, Hamming distance ≤ 8) are **advisory only**: the
  photo stays `SUITABLE` and records `near_duplicate_advisory` (distance/threshold/photo
  reference) in `measurements`; it is never downgraded to `REVIEW_REQUIRED`, never blocked
  from approval, and nothing is deleted. Near-duplicate detection is about image redundancy,
  never face identity.

## Enrollment status transitions (Person.enrollment_status)

```text
DRAFT (person created, no photos)
  │  photo uploads / approvals change
  ▼
NOT_READY (0–4 suitable approved photos)
  │  ≥ 5 suitable approved photos
  ▼
READY
  │  explicit "Enroll Approved Photos" action (Phase 6 only)
  ▼
ENROLLING ──success──▶ ENROLLED
     └──────failure──▶ ERROR   (specific FRIGATE_* reason; user may retry)
ENROLLED ──explicit removal──▶ NOT_READY (or READY if still ≥ 5 suitable approved photos)
```

- `DRAFT`/`NOT_READY`/`READY` are recomputed by the ReadinessService whenever photos are
  uploaded, approved, or deleted.
- `ENROLLING`/`ENROLLED`/`ERROR` are written only by the enrollment service (Phase 6).
- `READY` never transitions to anything automatically (spec FR-022, SC-006).
- `ERROR` retains the person's photos and readiness so the user can retry.

## Readiness calculation

```text
approved_suitable_count = count(photos where quality_status == SUITABLE AND approved == true,
                                 counting each exact-duplicate_group at most once)
required_min   = 5   (configuration constant; matches feature 001's T034 gate)

status = DRAFT      if approved_suitable_count == 0 AND photo_count == 0
       = NOT_READY  if approved_suitable_count < required_min
       = READY      if approved_suitable_count >= required_min
```

Readiness is recomputed (and `READINESS_CHANGED` audited only on an effective
NOT_READY ↔ READY transition) whenever photos are uploaded, approved, unapproved, deleted,
or reanalyzed into a different quality state. `READY` means "a sufficient explicitly
approved photo set exists locally" — it never triggers enrollment (FR-022, SC-006): no
Frigate calls, no embeddings, `frigate_identity_name` stays NULL, `enrolled_in_frigate`
stays false. A disabled person keeps their readiness state (enabled/disabled is orthogonal).

Readiness response includes: `approved_suitable_count`, `minimum_required`, `status`,
`remaining_required`, `total_uploaded`, `suitable_count`, `approved_count`,
`review_required_count`, `unsuitable_count`, `enrollment_enabled: false`, `missing` (e.g.
"more suitable photos", "angle/expression diversity"), and a `diversity` review object
(`{ has_multiple_angles: bool | null, has_expression_variation: bool | null, notes }`) —
diversity is review metadata, not a blocking criterion in the MVP (spec US4).

## Entity relationship summary

```text
Person (1) ──< (many) EnrollmentPhoto
Person (1) ──< (many) AuditLogEntry (subject referenced via entity_type/entity_id)
EnrollmentPhoto (many) ──> Person (via person_id)
RelationshipCategory: config list, referenced by Person.relationship (not a FK table)
```

## Non-goals in this model

- No tables for recognition results, events, or notifications (those belong to feature 001).
- No embeddings stored locally — Frigate owns embeddings in its own library/volume.
- No automatic person creation from events (spec FR-027).