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

## Gating

**Gate G1 = PASS.** Phase 2 (People Management) is actionable pending the user's review of
this report (hard stop per the approved implementation authorization).

## Blocking issues

None. One non-blocking observation: the pre-existing `*:8000` listener noted above (now
gone) — worth confirming nothing else on this Mac expects port 8000.