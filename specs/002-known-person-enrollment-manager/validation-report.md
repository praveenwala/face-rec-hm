# Validation Report: Known Person Enrollment Manager

**Feature**: [Known Person Enrollment Manager](./spec.md)
**Date**: 2026-09-10
**Executed by**: Claude Code, per tasks T001–T008 (Phase 1 — Foundation)

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

## Gating

**Gate G1 = PASS** (Phase 1 report above).
**Gate G2 = PASS.** Phase 3 (Photo Management) is actionable pending the user's review of
this report (hard stop per the approved implementation authorization; nothing committed or
pushed for Phase 2).

## Blocking issues

None. Non-blocking observations:
- The pre-existing `*:8000` listener noted in Phase 1 (now gone).
- Pydantic `ctx` serialization fix (T010) is a small but real correctness improvement to
  the error envelope — worth remembering in Phase 3 (same handler serves photo validation
  errors).
- This sandbox reaps background dev servers between shell commands, so the live
  proxy/networking checks were performed within single commands; on a normal Mac the two
  terminal workflow (`run.sh` + `npm run dev`) persists as documented.