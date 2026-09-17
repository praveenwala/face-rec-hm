# Known Person Enrollment Manager — How to Run

Local-only management surface for the known-person enrollment photo library
(feature `002-known-person-enrollment-manager`). It is a **localhost-only** web
app: the backend binds to `127.0.0.1:8000` and the frontend dev server to
`127.0.0.1:5173`. It never binds to `0.0.0.0` and must never be exposed to a LAN
or the Internet.

> **Phase 6 (Frigate enrollment) — current status.** Frigate face-management/enrollment
> integration **exists and is real** (`POST /api/people/{id}/enroll`,
> `DELETE /api/people/{id}/enrollment`, `GET /api/frigate/status`) — it is not a future or
> unimplemented stub, and this app does call real Frigate face-management APIs when the
> gate below is on. Enrollment is **explicit and feature-gated**: the single gate is the
> `FRIGATE_ENROLLMENT_ENABLED` environment variable, which **defaults to `false`**. The
> steady state is **gate OFF** — enrollment/removal only ever run during an explicitly
> authorized, bounded test/enrollment window, then the gate is restored to OFF. While OFF,
> every mutating call refuses up-front (`501 FEATURE_NOT_ENABLED`) and performs zero
> Frigate mutation; this app never touches Home Assistant either way. Reaching
> `READY FOR ENROLLMENT` in the UI only means "a sufficient explicitly approved photo set
> exists locally" — it never triggers any biometric action by itself.
>
> **What has been validated:** spec `001-front-door-person-identification`'s T034 and
> T039–T042 exercised real enroll/refine/remove/no-silent-creation behavior through this
> exact app. A separate live regression ("T041 bounded live regression") validated identity
> removal plus identity-scoped `faces/train/` cleanup against this deployed stack.
> **What has NOT been validated:** T035 (stable Known-person recognition — a real event
> reliably producing a matching `sub_label`) remains pending/deferred in every environment,
> dev and production. **Successful enrollment/removal is not evidence of Known-path
> recognition** — treat them as separate concerns; do not read one as implying the other.
> **No automation in this project may let physical access, unlock, or disarm actions depend
> on face recognition** — this remains a notification-only capability by design.

## Requirements

- macOS (Intel POC host) with Python ≥ 3.11 and Node.js LTS + npm (native mode)
  **or** Docker with Docker Compose (containerized mode).
- No Docker required for native mode. The app is independent of the Feature 001
  Docker stack for everything except actually reaching Frigate — enrollment/removal
  calls (Phase 6, gated OFF by default) need the Feature 001 stack running and network-
  reachable; all other functionality works without it.
- One-time model fetch (needed for automatic photo-quality analysis):

```bash
enrollment-app/scripts/fetch_models.sh
```

This downloads Frigate's YuNet face detector (`facedet.onnx`) into the gitignored
app cache at `enrollment-app/data/models/facedet.onnx` (checksum-verified).
Without it, uploads still work but stay `PENDING` with
`analysis_error: FACE_DETECTOR_UNAVAILABLE`.

## Run with Docker (all-in-one)

Build and start the whole app (backend + frontend) with one command:

```bash
docker compose -f docker-compose.enrollment.yml up -d --build
```

Then open **http://127.0.0.1:8090** in your browser.

- The UI (nginx serving the built React app) is exposed at `127.0.0.1:8090` and
  proxies `/api` to the backend; the backend API is also reachable directly at
  `127.0.0.1:8000`. **Both bindings are loopback-only** — nothing is exposed to
  the LAN or the Internet.
- Runtime data (`app.db`, `people/`, `models/`) is the same gitignored
  `enrollment-app/data/` directory, bind-mounted read-write — it persists across
  container restarts and is shared with the native workflow. Fetch the model on
  the host first (`scripts/fetch_models.sh`) or uploads will stay `PENDING`.
- Stop: `docker compose -f docker-compose.enrollment.yml down`
  (add `-v` to also remove the named volumes — none are used here; data lives in
  the bind mount, so `down` alone never deletes photos).
- Logs: `docker compose -f docker-compose.enrollment.yml logs -f`.
- This stack is **separate from** `docker-compose.yml` (Feature 001's Frigate/
  Mosquitto/HA stack). It never talks to it; run either or both. If you run both,
  note the enrollment stack binds host ports 8000/8090 and the 001 stack binds
  1883/5000/8554/8124/18554 — no overlap.

## Start the app (two terminals)

```bash
# Terminal 1 — backend (bootstraps .venv on first run, then uvicorn)
cd enrollment-app/backend
./run.sh

# Terminal 2 — frontend dev server (proxies /api → the backend)
cd enrollment-app/frontend
npm run dev
```

Then open **http://127.0.0.1:5173** in your browser.

## Verify it is up

```bash
# Backend health
curl -s http://127.0.0.1:8000/api/health
# → {"status":"ok","app_version":"0.1.0","database":"ok","frigate":{"reachable":null}}

# Loopback-only check (must show 127.0.0.1, never * or 0.0.0.0)
lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8000|5173)\b'

# Frontend reachable
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5173/   # → 200
```

## Typical workflow

1. **People page** → *Add Person* (display name + relationship — Family /
   Friend / Neighbor / Other Known, selected manually, never inferred).
2. **Open the person** → *Photos* → drag & drop or pick JPEG/PNG/WEBP files.
   Each upload is analyzed automatically: ✓ Suitable / ✕ Unsuitable /
   ⚠ Review required / Pending with a reason and expandable measurements.
3. **Approve** the ✓ Suitable photos (explicit human action — only SUITABLE
   photos show an Approve button; nothing is ever auto-approved).
4. **Readiness card** shows `n / 5 approved suitable photos` →
   `NOT READY` below 5, `READY FOR ENROLLMENT` at 5+ **distinct** approved
   suitable photos. (Exact duplicate uploads share a SHA-256 `duplicate_group`
   and count once; near-duplicates are advisory only — a similar photo stays
   Suitable and can be approved.)

## Troubleshooting

- **"site can't be reached" / port refused**: the backend and/or frontend are
  not running (or were killed). Start both terminals again and re-check the
  `lsof`/`curl` commands above. On some hosts, long-lived background processes
  started with `nohup … &` from a single shell may be reaped — the reliable
  way to keep them alive is the **two-terminal** workflow above.
- **Port already in use**: `lsof -nP -iTCP:8000 -sTCP:LISTEN` — if a stale
  process holds it, stop it (only if it is your own stale run) and retry.
- **Uploads stay PENDING**: run `enrollment-app/scripts/fetch_models.sh` and
  re-analyze (Re-analyze button / `POST …/photos/{id}/analyze`).
- **Readiness won't reach READY**: check the readiness card — you need 5
  *distinct approved suitable* photos (exact duplicates count once); only
  `SUITABLE AND approved` photos count.
- **UI shows stale data after approving**: refresh the page.

## Privacy rules (non-negotiable)

- All runtime data lives under `enrollment-app/data/` (`app.db`, `people/`,
  `models/`, thumbnails) — this directory is **gitignored**; never commit it.
- Photos are private biometric media. They are stored byte-for-byte under
  `data/people/<uuid>/original/` with randomized filenames; the original
  filename is metadata only. Never copy these files into tracked fixtures,
  logs, or reports.
- The API exposes metadata only (no filesystem paths, no image bytes except
  the explicit file/thumbnail endpoints, which are loopback-only).
- `frigate_identity_name` stays NULL and `enrolled_in_frigate` stays false unless the
  `FRIGATE_ENROLLMENT_ENABLED` gate is explicitly turned on for a bounded window and
  enrollment is explicitly triggered — never automatically, never as a side effect of
  reaching readiness.

## Tests

```bash
cd enrollment-app/backend && source .venv/bin/activate
python -m pytest app/tests            # 116 tests (Phases 1–5)
```

## Related documentation

- Feature spec, plan, tasks, contracts, and the living validation report:
  `specs/002-known-person-enrollment-manager/`
- End-to-end local validation walk-through: `specs/002-known-person-enrollment-manager/quickstart.md`