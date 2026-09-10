# Contract: Frigate Enrollment Service Abstraction (Phase 6 design basis)

All Frigate interaction lives behind a single service class (`FrigateEnrollmentService` in
`enrollment-app/backend/app/services/frigate_service.py`). Raw Frigate HTTP calls must never
appear in controllers, routers, or UI code (spec FR-028).

**Phase 6 is BLOCKED** until the user explicitly approves executing it (spec FR-030, plan.md
Phase 6 gate). This contract is the design basis for that phase; the endpoint list below is
derived from the documented Frigate API (docs.frigate.video/integrations/api) and **MUST be
re-verified against the installed Frigate 0.17.2 runtime's OpenAPI schema
(`GET http://localhost:5001/api/openapi.json`) before any integration code is written** —
that verification is task T034 (spec FR-029, constitution VI.3: no invented endpoints).

## Service responsibilities (eventually)

| Method | Purpose | Frigate endpoint (documented basis) |
|---|---|---|
| `health()` | Is Frigate reachable + what version | `GET /api/` (returns "Frigate is running. Alive and healthy!"), `GET /api/version` |
| `list_identities()` | All registered face names (+ their image files) | `GET /api/faces` → `{ name: [filenames...] }` |
| `create_identity(name)` | Register a new face name | `POST /api/faces/{name}/create` |
| `register_face(name, image)` | Submit one approved photo to a face | `POST /api/faces/{name}/register` (payload verified at T034) |
| `train_face(name, image_file \| event_id)` | Classify + save a training image (the official "add training image to a face" path) | `POST /api/faces/train/{name}/classify` — accepts a training file from the train directory or an `event_id` |
| `remove_identity(name)` | Deregister the face's training files | `POST /api/faces/{name}/delete` with `{"ids": [...]}` — full-name removal semantics (empty library → name gone?) verified at T034 |
| `reprocess(name)` | Reprocess a training image after a failed classification | `POST /api/faces/reprocess` |
| `recognize(face_image)` | Post-enrollment verification (optional) | `POST /api/faces/recognize` (classification, not enrollment) |
| `reindex()` | Rebuild embeddings after library changes | `PUT /api/reindex` (verify availability in 0.17.2) |
| `reconcile()` | Compare app persons vs. `GET /api/faces`; surface drift, never auto-mutate Frigate | uses `list_identities()` |

## Enrollment flow (Phase 6, designed, not executed)

```text
user clicks "Enroll Approved Photos" (explicit action; person must be READY)
  → POST /api/people/{id}/enroll (app API)
    → status ENROLLING (persisted)
    → resolve frigate_identity_name (suggested from display_name; user-editable; unique
      against app table AND Frigate's /api/faces → else 409 IDENTITY_CONFLICT)
    → create_identity(name)
    → for each suitable AND approved photo:
        normalize copy → register_face(name, image)  (or train_face per T034 findings)
        mark photo.enrolled_in_frigate = true on success
    → reindex() if the runtime requires it after changes
    → status ENROLLED (or ERROR with FRIGATE_ENROLLMENT_FAILURE + partial-state cleanup
      guidance; no silent partial enrollment)
    → audit log: ENROLLMENT_REQUESTED / ENROLLMENT_COMPLETED / ENROLLMENT_FAILED
```

## Removal flow (Phase 6, designed, not executed)

```text
user clicks "Remove Enrollment" (explicit; distinct from disable and from delete)
  → DELETE /api/people/{id}/enrollment (app API)
    → remove_identity(frigate_identity_name)
    → reset person.enrollment_status to READY|NOT_READY (recomputed from remaining photos)
    → clear enrolled_in_frigate on photos
    → audit log: ENROLLMENT_REMOVED
Person delete with an active enrollment requires remove_enrollment=true (FR-026) and runs the
same removal first — no orphaned biometric enrollment.
```

## Identity mapping (recap from data-model.md)

| Concept | Owner | Notes |
|---|---|---|
| `Person.id` (UUID) | App | Storage + API identifier |
| `Person.display_name` | App | Editable metadata |
| `Person.frigate_identity_name` | App (set at enrollment) | Must equal the name in Frigate's library; unique; rename of display_name never changes it |
| Recognition `sub_label` | Frigate | Frigate reports `frigate_identity_name` |

## Failure states (constitution IV.2 — every dependency needs a failure state)

- Frigate unreachable → `FRIGATE_UNAVAILABLE` (503); app UI shows degraded state; person stays
  `READY`; no partial writes attempted.
- Individual photo submission fails mid-enrollment → `FRIGATE_ENROLLMENT_FAILURE`; already-
  submitted photos marked `enrolled_in_frigate`; person → `ERROR`; retry allowed.
- Drift between app and Frigate (identity exists in Frigate but not app, or vice versa) →
  surfaced by `reconcile()`, never auto-resolved (constitution II.1 — no silent identity
  creation/deletion).
- Face recognition disabled in Frigate config → enrollment endpoints report a clear error
  (verified at T034; the POC config has recognition enabled per 001's T032).