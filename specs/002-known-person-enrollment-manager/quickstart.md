# Quickstart: Validating the Known Person Enrollment Manager (Phases 1–5)

This validates feature 002's local management surface end-to-end: backend API, React UI,
private storage, photo upload + quality validation, approval, and the readiness gate. It does
**not** cover Frigate enrollment (Phase 6 — blocked until explicitly approved) or Home
Assistant integration (Phase 7 — not implemented). It also does not touch feature 001's
pipeline; run its harness before and after to confirm `OVERALL PASS` is unchanged (spec
SC-012).

## Prerequisites

- macOS (Intel POC host), Python >= 3.11 (`python3 --version`; if older, `brew install
  python@3.12` — the venv must use a 3.11+ interpreter), Node.js LTS + npm.
- ffmpeg available (already a project dependency from feature 001's PD-02) for HEIC
  normalization.
- No Docker required for this app (native venv; the 001 stack may be up or down — the app is
  independent until Phase 6).

## Setup

Prerequisites: macOS, Python >= 3.11 (`python3 --version`; if older, `brew install
python@3.12`), Node.js LTS + npm, ffmpeg (for Phase 4 HEIC normalization; already a project
dependency). No Docker required for this app — it is independent of the 001 stack until
Phase 6.

```bash
# Backend — first run only: creates .venv and installs pinned deps (run.sh does this
# automatically; manual alternative shown below)
cd enrollment-app/backend
./run.sh                      # bootstraps .venv on first run, then starts uvicorn

# Manual alternative:
#   python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# Frontend — first run only:
cd ../frontend
npm install
```

## Start (two terminals)

```bash
# Terminal 1 — backend on 127.0.0.1:8000 (loopback only)
cd enrollment-app/backend
./run.sh

# Terminal 2 — frontend dev server (proxies /api → the backend)
cd enrollment-app/frontend
npm run dev                   # http://127.0.0.1:5173
```

Expected: the backend answers `GET http://127.0.0.1:8000/api/health` →
`{"status":"ok","app_version":"0.1.0","database":"ok","frigate":{"reachable":null}}`;
the UI loads at `127.0.0.1:5173`. Verify loopback-only (spec SC-011):

```bash
lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8000|5173)\b'   # must show 127.0.0.1, never * or 0.0.0.0
```

## Phase 1 validation (G1)

```bash
curl -s http://127.0.0.1:8000/api/health        # → status ok, database ok
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  http://127.0.0.1:8000/api/people/x/enroll      # → 501 (FEATURE_NOT_ENABLED, Phase 6 blocked)

cd enrollment-app/backend && source .venv/bin/activate
python -m pytest app/tests -v                     # → 49 passed (Phases 1–2)

cd <repo root>
git status --short                                 # → no enrollment-app/data/ content
git check-ignore enrollment-app/data/app.db        # → ignored (exit 0)
```

## Phase 2 validation (G2)

```bash
# People CRUD (synthetic names only)
curl -s http://127.0.0.1:8000/api/relationships      # → the four categories
curl -s -X POST http://127.0.0.1:8000/api/people \
  -H 'Content-Type: application/json' \
  -d '{"display_name":"Test Person","relationship":"Family"}'   # → 201, frigate_identity_name null
curl -s http://127.0.0.1:8000/api/people            # → flat list (grouping is UI-side)
curl -s -X PATCH http://127.0.0.1:8000/api/people/<id> \
  -H 'Content-Type: application/json' -d '{"relationship":"Friend","enabled":false}'
curl -s "http://127.0.0.1:8000/api/audit"          # → PERSON_CREATED, RELATIONSHIP_CHANGED, ...
curl -s -X DELETE http://127.0.0.1:8000/api/people/<id>   # → 204
```

UI: open `127.0.0.1:5173` → People page groups cards under **Family / Friends / Neighbors /
Other Known**; Add Person, Edit (rename/relationship/enable), Disable/Enable, and Delete
(with confirmation) all work. Delete refuses with `409 ENROLLED_PERSON_DELETE_REFUSED` if a
person is ever `ENROLLED` (not reachable before Phase 6).

## Automated tests (all phases)

```bash
cd enrollment-app/backend && source .venv/bin/activate
python -m pytest app/tests -v
```

Fixtures are generated public-domain/synthetic images (never household biometric media). The
privacy tests assert the data path is gitignored and that deletion removes DB rows and files.

## Walk-through (maps to spec US1–US6 — steps 1 and 5 live; 2–4 land with Phases 3–5)

> Steps 1 and 5 (people management, US1/US5/US6) are implemented as of Phase 2 — see the
> Phase 2 validation section above. Steps 2–4 (photos, quality, readiness) will be exercised
> when Phases 3–5 land.

1. **Create a person (US1)**: Add Person → display name + relationship (Family/Friend/
   Neighbor/Other Known). Verify the People page shows the card grouped under the right
   heading (US6) with `0 suitable photos`, status `DRAFT`/`NOT_READY`. Confirm an audit entry
   `PERSON_CREATED` exists and that creating the person performed **no** Frigate action
   (SC-001 — no biometric data created anywhere).
2. **Upload photos (US2)**: Drag a few JPEG/PNG/WEBP files into the dropzone (multi-file).
   Each appears with its per-photo result — `SUITABLE`, `UNSUITABLE`, or `REVIEW_REQUIRED`
   and a reason (US3). Confirm the originals are byte-identical to what you uploaded
   (FR-011). HEIC file → normalized JPEG copy in `normalized/`, original untouched (or a clear
   `UNSUPPORTED_FORMAT` if conversion fails).
3. **Quality classifications (US3)**: Upload deliberately bad files — a blank/corrupt file
   (`MEDIA_DECODE_FAILURE` or `UNSUPPORTED_FORMAT`, never `NO_FACE`), a very small/tiny face
   (`FACE_TOO_SMALL`), a blurry shot (`TOO_BLURRY`), and a photo with two people
   (`REVIEW_REQUIRED` + `MULTIPLE_FACES` — not silently accepted, FR-017). Measurements and
   judgments render as separate sections (FR-014).
4. **Approval + readiness (US4)**: Approve suitable photos. Readiness badge shows
   `n / 5 suitable photos` and `NOT_READY` below 5; at 5+ approved suitable photos it shows
   `READY`. Confirm `UNSUITABLE`/`REVIEW_REQUIRED`/unapproved photos never count (US4
   scenario 3), and that reaching `READY` does nothing by itself — no enrollment button fires,
   no Frigate API is called (SC-006).
5. **Manage (US5/US6)**: Rename the person (verify `frigate_identity_name` — not yet set —
   would be untouched; no re-enrollment concept applies pre-Phase-6), change relationship
   (card moves groups), disable (record preserved, marked disabled), delete with confirmation
   (record + photo rows + stored files gone; audit entry `PERSON_DELETED`).

## Privacy verification (spec SC-007, SC-010)

```bash
git status --short        # no enrollment-app/data/ content appears
git check-ignore enrollment-app/data/app.db   # → ignored
find enrollment-app/data  # your photos exist on disk, outside git
```

Also confirm: no endpoint or UI path creates a Person from recognition events (there is no
such path — unknown visitors stay events; SC-010).

## Feature 001 regression (spec SC-012)

With the 001 stack running:

```bash
tests/phase1/run_harness.sh all
```

Expected: `OVERALL PASS`, unchanged from before feature 002 work. If the enrollment app is
running at the same time, results must be identical (the app never reads or writes 001's
config, MQTT, or media).

## What is NOT validated here (gated)

- Frigate enrollment (Phase 6) — blocked pending explicit approval + task T034 API verification.
  No test in this quickstart creates a Frigate identity (SC-014).
- Home Assistant relationship automation (Phase 7) — designed for, not implemented.
- Feature 001's T034 — remains NOT STARTED; the enrollment-media gate
  (`ENROLLMENT_MEDIA_NEEDS_MORE_PHOTOS`) stays in force until the user decides how this app
  resolves it.

## Record the result

Fill in `validation-report.md` with the outcome of each step (living document, per feature
001's convention) before the corresponding phase is marked complete.