# Contract: REST API — Known Person Enrollment Manager

The FastAPI backend exposes this JSON API on `http://127.0.0.1:8000/api` (loopback only —
spec FR-002, SC-011). All request/response bodies are JSON except the photo-upload endpoint
(multipart/form-data) and the file/thumbnail endpoints (image bytes). The frontend consumes
exactly this contract; the Frigate service abstraction is a separate contract
([frigate-enrollment-interface.md](./frigate-enrollment-interface.md)).

## Error envelope

Every error response uses:

```json
{
  "error": {
    "code": "FACE_TOO_SMALL",
    "message": "The primary face occupies too little of the frame (0.004 of image area).",
    "details": {}
  }
}
```

| HTTP status | Codes used |
|---|---|
| 400 | `VALIDATION_ERROR`, `UNSUPPORTED_FORMAT` (upload-level), `IDENTITY_CONFLICT` (create-level), `QUALITY_REJECTED` |
| 404 | `PERSON_NOT_FOUND`, `PHOTO_NOT_FOUND` |
| 409 | `IDENTITY_CONFLICT` (enrollment-level), `ENROLLED_PERSON_DELETE_REFUSED` |
| 422 | `MEDIA_DECODE_FAILURE`, `NO_FACE_DETECTED`, `MULTIPLE_FACES`, `FACE_TOO_SMALL` (when reported as a blocking error), `NOT_READY` |
| 500 | `STORAGE_FAILURE`, `DATABASE_FAILURE` |
| 503 | `FRIGATE_UNAVAILABLE`, `FRIGATE_ENROLLMENT_FAILURE` |

Per-photo quality outcomes from a multi-upload are **data, not transport errors**: the upload
endpoint returns `201` with one result object per file, each carrying its own
`quality_status`/`rejection_reason`. The HTTP error codes above apply to whole-request
failures (e.g. zero readable files, storage failure).

## Endpoints

### System

| Method & path | Purpose |
|---|---|
| `GET /api/health` | `{ "status": "ok", "app_version": "...", "frigate": { "reachable": null } }` — `frigate.reachable` is populated only after Phase 6 wiring; `null` before |
| `GET /api/relationships` | `{ "relationships": ["Family", "Friend", "Neighbor", "Other Known"] }` — the configurable category list |
| `GET /api/audit?person_id=<uuid>` | `{ "entries": [ { "id", "timestamp", "action", "entity_type", "entity_id", "details" } ] }` — newest first; no image bytes, no secrets. (`entity_type`/`entity_id` replace the draft's `person_id`/`photo_id` — user-approved Phase 1 deviation; `details` is JSON metadata only) |

### People

| Method & path | Body | Returns |
|---|---|---|
| `GET /api/people` | — | `{ "people": [ PersonSummary ] }` — each summary: `id`, `display_name`, `relationship`, `enabled`, `enrollment_status`, `suitable_count`, `photo_count`, `representative_photo_url` |
| `POST /api/people` | `{ "display_name": str, "relationship": "Family\|Friend\|Neighbor\|Other Known" }` | `201` → Person; `400` validation; **never performs any enrollment action** |
| `GET /api/people/{id}` | — | Person detail: all fields incl. `frigate_identity_name`, `enrollment_status`, counts |
| `PATCH /api/people/{id}` | any of `{ "display_name"?, "relationship"?, "enabled"? }` | Person; renaming `display_name` never touches `frigate_identity_name` |
| `DELETE /api/people/{id}` | (query `?remove_enrollment=true` reserved for Phase 6) | `204`; `409 ENROLLED_PERSON_DELETE_REFUSED` when `enrollment_status == ENROLLED` (FR-026). **Phase-2 scope note:** while Phase 6 enrollment removal is blocked, delete is refused whenever `ENROLLED` — even with `remove_enrollment=true` — because honoring that flag would require Phase 6 Frigate removal and would otherwise orphan a biometric enrollment. No person can reach `ENROLLED` in Phases 1–5 |

### Photos (per person)

| Method & path | Body | Returns |
|---|---|---|
| `POST /api/people/{id}/photos` | `multipart/form-data`, field `files` (one or more) | `201` → `{ "results": [ { "photo_id", "original_filename", "quality_status", "rejection_reason", "measurements", "approved": false } ] }` — one result per file; upload alone never approves/enrolls |
| `GET /api/people/{id}/photos` | — | `{ "photos": [ PhotoSummary ] }` — metadata only (no bytes) |
| `GET /api/people/{id}/photos/{photo_id}` | — | Photo metadata detail incl. all measurements |
| `GET /api/people/{id}/photos/{photo_id}/file?kind=original\|normalized` | — | Image bytes (JPEG/PNG/etc.); loopback only |
| `GET /api/people/{id}/photos/{photo_id}/thumbnail` | — | Small preview (max ~300px) for the photo list/cards |
| `POST /api/people/{id}/photos/{photo_id}/approve` | — | Photo; sets `approved=true` — an **explicit user action**, never automatic (FR-019/FR-023); updates readiness |
| `POST /api/people/{id}/photos/{photo_id}/unapprove` | — | Photo; sets `approved=false` (approval revoked); updates readiness |
| `DELETE /api/people/{id}/photos/{photo_id}` | — | `204`; removes DB row + files in `original/`, `normalized/`, `approved/` |

### Readiness

| Method & path | Returns |
|---|---|
| `GET /api/people/{id}/readiness` | `{ "person_id", "suitable_count", "required_min": 5, "status": "DRAFT\|NOT_READY\|READY", "missing": [...], "diversity": {...} }` |

### Enrollment (Phase 6 — BLOCKED until explicitly approved)

| Method & path | Returns |
|---|---|
| `POST /api/people/{id}/enroll` | `200` → `{ "enrollment_status": "ENROLLED", "frigate_identity_name": "..." }`; `422 NOT_READY`; `409 IDENTITY_CONFLICT`; `503 FRIGATE_UNAVAILABLE / FRIGATE_ENROLLMENT_FAILURE` |
| `DELETE /api/people/{id}/enrollment` | `204`; removes the Frigate identity and resets person status (FR-030 gating applies) |
| `GET /api/frigate/status` | `{ "reachable": bool, "version": str, "identities": [str] }` — reconciliation source (Phase 6) |

## Validation rules carried from the spec

- `relationship` must be one of the values returned by `GET /api/relationships` (FR-004).
- `display_name` is required, non-empty, max length enforced (FR-003).
- No endpoint accepts or returns raw photo bytes except the explicit file/thumbnail endpoints
  (FR-010).
- No endpoint creates, deletes, or mutates Frigate state except the three Phase 6 endpoints,
  and those are blocked until approval (FR-030).
- All mutations are recorded in the audit log (FR-031).