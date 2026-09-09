# Local Mac Testing Guide

**Feature**: [Front Door Person Identification](../../specs/001-front-door-person-identification/spec.md)
**Companion documents**: [plan.md](../../specs/001-front-door-person-identification/plan.md) ·
[tasks.md](../../specs/001-front-door-person-identification/tasks.md) ·
[pre-development-validation.md](../../specs/001-front-door-person-identification/pre-development-validation.md) ·
[validation-report.md](../../specs/001-front-door-person-identification/validation-report.md)

> **DO NOT START T020 UNTIL T019 = PASS.** Check
> [validation-report.md](../../specs/001-front-door-person-identification/validation-report.md)
> for the current, authoritative pass/fail state of every check in this guide — this document
> explains *how* to run the tests, that document records *whether they currently pass*.

## 1. Purpose

This local environment exists to prove the pipeline mechanics — container orchestration,
video ingestion, person detection, MQTT transport, and Home Assistant visibility — work
correctly *before* any of it touches your real house. Nothing in this guide talks to your
production Home Assistant or Ring devices.

```text
Mac development/testing
        ↓
Docker
        ↓
Mosquitto (isolated) + Frigate + throwaway Home Assistant
        ↓
sample video (looped, local file — not a live camera)
        ↓
person detection
        ↓
MQTT
        ↓
throwaway Home Assistant (disposable, local only)
```

Later, once this is proven, the production pipeline (documented separately in
[production-deployment.md](../production/production-deployment.md)) looks like this instead:

```text
Ring Front Door
 ↓
Ring-MQTT / supported video bridge
 ↓
Frigate (dedicated AI host — not this Mac, not the Pi)
 ↓
MQTT
 ↓
Raspberry Pi 3 running the real Home Assistant
```

The Mac, Mosquitto, Frigate, and the throwaway Home Assistant instance used here are **all
disposable and local-only**. Nothing here is production. This satisfies constitution
Principle I.1 (Home Assistant remains the control plane) and I.2 (AI workloads run
separately) by construction — this Phase 1 environment never runs on, or connects to, the
Raspberry Pi 3.

## 2. Prerequisites

Verified on this Mac (see `validation-report.md` for the full inventory):

| Requirement | Check command | Confirmed version (this Mac) |
|---|---|---|
| Intel MacBook Pro | `sysctl -n machdep.cpu.brand_string` | Intel(R) Core(TM) i9-9980HK |
| Docker Desktop | `docker --version` | 29.4.3 |
| Docker Compose | `docker compose version` | v5.1.4 |
| Git | `git --version` | 2.44.0 |
| FFmpeg | `ffmpeg -version` | 9.0.1 |
| ffprobe | `ffprobe -version` | 9.0.1 |
| mosquitto_pub | `mosquitto_pub --help` (prints usage; no `--version` flag) | mosquitto 2.1.2 |
| mosquitto_sub | `mosquitto_sub --help` | mosquitto 2.1.2 |
| Sufficient disk space | `df -H /` | ~16 GB free at last check — **watch this**; Frigate's own clip/db storage and sample media both consume disk |

If `ffmpeg`/`ffprobe`/`mosquitto_pub`/`mosquitto_sub` are missing, install via Homebrew:

```bash
brew install ffmpeg mosquitto
```

Docker Desktop must actually be *running* (not just installed) — `docker info` will hang or
error if the daemon isn't up. If needed: `open -a Docker`, then wait ~10-20s and retry.

## 3. Starting the environment

From the repository root:

```bash
docker compose start
```

Use `docker compose start` when the containers already exist and were previously stopped with
`docker compose stop` — it resumes them as-is, with all prior state (Frigate's database,
throwaway HA's onboarding, etc.) intact.

```bash
docker compose up -d
```

Use `docker compose up -d` instead when: this is the *first* time starting the stack, you've
changed `docker-compose.yml` or any of the three services' config files and need them
recreated, or a service doesn't exist yet (e.g. after a fresh `git clone`). It creates
whatever's missing/changed and starts everything, leaving unaffected services alone.

## 4. Checking status

```bash
docker compose ps
```

Healthy output looks like this (actual output from this environment):

```text
NAME                           IMAGE                                             STATUS
face-rec-phase1-frigate        ghcr.io/blakeblackshear/frigate:0.15.1            Up ... (healthy)
face-rec-phase1-ha-throwaway   ghcr.io/home-assistant/home-assistant:2024.12.5   Up ...
face-rec-phase1-mosquitto      eclipse-mosquitto:2.0.18                          Up ...
```

- Frigate shows `(healthy)` once its internal healthcheck passes — a few seconds after start.
- Mosquitto and the throwaway HA don't define a Docker healthcheck in this compose file, so
  `Up ...` (no restart count climbing, see below) is the "healthy" signal for them.
- If any service instead cycles `Restarting` repeatedly, see §16 Troubleshooting.
- To confirm none are crash-looping: `docker inspect <container> --format '{{.RestartCount}}'`
  should read `0` for all three during normal operation.

## 5. Opening services

These URLs come directly from `docker-compose.yml` and `.env.example` — verify against your
own `.env` if you've changed the defaults there.

- **Frigate**: <http://localhost:5001> (mapped from container port 5000; moved off the
  default 5000 because macOS Control Center's AirPlay Receiver already uses it — see §16)
- **Throwaway Home Assistant**: <http://localhost:8124> (mapped from container port 8123).
  This is a disposable instance for Phase 1 only — it is a separate instance from your real
  production Home Assistant at `192.168.68.103`, not a view into it.

## 6. Checking logs

```bash
docker compose logs frigate
docker compose logs --tail=100 frigate
docker compose logs -f frigate          # follow, live

docker compose logs mosquitto
docker compose logs --tail=100 mosquitto
docker compose logs -f mosquitto

docker compose logs ha-throwaway
docker compose logs --tail=100 ha-throwaway
docker compose logs -f ha-throwaway
```

**Expected (not a problem) until you've provided sample media (T008):**

```text
WRN [rtsp] error="streams: exec: ffmpeg version ..." stream=front_door_test
frigate.video  ERROR: front_door: Unable to read frames from ffmpeg process.
frigate.video  ERROR: front_door: ffmpeg process is not running. exiting capture thread...
watchdog.front_door  ERROR: Ffmpeg process crashed unexpectedly for front_door.
ffmpeg.front_door.detect  ERROR: Error opening input file rtsp://127.0.0.1:8554/front_door_test.
```

This is Frigate retrying every ~10 seconds because
`tests/phase1/test-media/known-person-walk.mp4` doesn't exist yet — it is *not* a
configuration bug, and it does not restart the container itself (check restart count, not
just log noise).

**Not expected — investigate immediately if you see these:**

- Any Python traceback from `frigate.app` at startup (config parse failure)
- `Invalid substitution found` (a real go2rtc config bug — see §16)
- `executable file not found in $PATH` (a real ffmpeg-path bug — see §16)
- The container's `RestartCount` climbing, or status stuck on `Restarting`
- Mosquitto logging repeated `Client ... disconnected` for a client you didn't intentionally
  disconnect

## 7. MQTT smoke test

The Phase 1 broker is isolated and has **no authentication configured**
(`mosquitto/config/mosquitto.conf` — deliberately, since it's local-Docker-network-only and
never production; see that file's own warning comment). If you later add authentication,
replace the commands below with `-u "$MQTT_USER" -P "$MQTT_PASS"` reading from your
gitignored `.env` — never hardcode credentials into a command you might paste elsewhere.

**Terminal 1:**

```bash
mosquitto_sub -h localhost -p 1883 -t 'phase1/smoketest' -C 1
```

**Terminal 2:**

```bash
mosquitto_pub -h localhost -p 1883 -t 'phase1/smoketest' -m 'hello from phase1'
```

**Expected output**: Terminal 1 prints `hello from phase1` and exits (the `-C 1` flag means
"exit after one message"). If Terminal 1 hangs indefinitely, see §16 ("MQTT connection
refused" / broker not reachable).

To watch real Frigate camera events on the same broker:

```bash
mosquitto_sub -h localhost -p 1883 -t 'frigate/events'
```

## 8. Sample-media location

```text
tests/phase1/test-media/
```

This directory is **private and gitignored** — confirmed via `git check-ignore -v
tests/phase1/test-media/`. Nothing placed here can be accidentally committed.

**NEVER commit:**
- faces / personal photos
- test videos
- Ring recordings
- biometric data of any kind

This is enforced by `.gitignore` (the `tests/phase1/test-media/` rule, plus broad `*.mp4`,
`*.jpg`, etc. patterns as defense in depth), not just convention — but always double-check
`git status` before committing, per the pre-commit checklist in
[CONTRIBUTING.md](../../CONTRIBUTING.md).

## 9. Testing a sample video manually

There are **two** scripts for this workflow: `scripts/loop-test-video.sh` (pre-flight probe /
decode validator, below) and `tests/phase1/run_harness.sh` (the automated MVP assertion
harness — see §9a).

`scripts/loop-test-video.sh`: It does **not** itself start a stream — it's a pre-flight
validator: it probes a candidate clip with `ffprobe`, does a real decode test with `ffmpeg`,
and tells you what to do next. The actual looping/streaming happens inside Frigate's own
bundled go2rtc, configured in `frigate/config/config.yml`.

1. **Copy your video into the test-media directory:**
   ```bash
   cp ~/Downloads/my-clip.mp4 tests/phase1/test-media/known-person-walk.mp4
   ```
   (Use the exact filename `frigate/config/config.yml`'s go2rtc `exec:` producer currently
   references — right now that's `known-person-walk.mp4`. Check the file if you're unsure;
   don't assume.)

2. **Probe and decode-test it:**
   ```bash
   scripts/loop-test-video.sh tests/phase1/test-media/known-person-walk.mp4
   ```
   This prints container/codec/resolution/fps/duration, attempts a real decode of a few
   frames, and reports `MEDIA_DECODE_FAILURE` (not `PERSON_NOT_DETECTED` — see §10) if the
   file can't be decoded.

3. **(Optional) preview it locally:**
   ```bash
   scripts/loop-test-video.sh tests/phase1/test-media/known-person-walk.mp4 --play
   ```

4. **Determine whether normalization is required.** If step 2 reports a codec/container
   outside §10's supported list, or decode fails, re-encode first:
   ```bash
   ffmpeg -i tests/phase1/test-media/original.mov -c:v libx264 -pix_fmt yuv420p \
     tests/phase1/test-media/known-person-walk.mp4
   ```

5. **Feed it into the existing test loop:** once the file exists at the path
   `frigate/config/config.yml` references, restart Frigate so it picks up the (already
   present, unchanged) config against the now-existing file:
   ```bash
   docker compose restart frigate
   ```

6. **Observe Frigate:**
   ```bash
   docker compose logs -f frigate
   ```
   You should stop seeing the "Unable to read frames" retry loop from §6, and instead see the
   camera processor running normally. Confirm via the stats API:
   ```bash
   curl -s http://localhost:5001/api/stats | python3 -m json.tool
   ```
   Look for `camera_fps` > 0 under `cameras.front_door`.

## 9a. Running the automated MVP harness

`tests/phase1/run_harness.sh` drives the looped go2rtc source and asserts on Frigate's MQTT
output — it is the automated form of the person-detection MVP checks (spec US1 SC-001 +
Acceptance Scenarios 3/4; tasks T020-T022/T025). It swaps the clip filename in
`frigate/config/config.yml`, restarts Frigate, observes `frigate/events`, and restores the
original clip on exit.

```bash
tests/phase1/run_harness.sh all        # run every assertion (positive + negative + identity-unavailable + failure-classes)
tests/phase1/run_harness.sh positive   # just the person-positive assertion
tests/phase1/run_harness.sh negative   # just the no-person assertion
tests/phase1/run_harness.sh identity-unavailable   # stop-Frigate classification + recovery
tests/phase1/run_harness.sh failure-classes        # MEDIA_DECODE/STREAM/EVENT_DELIVERY classifications
```

Every outcome is classified explicitly — never collapsed (constitution IV.3):

| Outcome | Meaning |
|---|---|
| `PERSON_PRESENT` | person-labeled event observed on `frigate/events` |
| `PERSON_NOT_DETECTED` | Frigate healthy + ingesting, but no person event in the window |
| `MEDIA_DECODE_FAILURE` | the clip itself couldn't be probed/decoded |
| `STREAM_FAILURE` | Frigate down or not ingesting (subsystem unavailable) |
| `EVENT_DELIVERY_FAILURE` | broker unreachable or subscription failed |

Expected (as of the T019-passing baseline): `all` prints OVERALL PASS. Default clips are
`known-person-walk.mp4` (positive) and `videos/derived-no-person-segment-1.mp4` (negative),
overridable via `POSITIVE_CLIP`/`NEGATIVE_CLIP` env vars. Observation windows default to
30 s (positive) and 45 s (negative) — do not shrink these just to make a flaky pass.

**Host-side broker endpoint**: the harness connects to `127.0.0.1:1883` (the Phase 1
broker's host-published port). It deliberately does **not** inherit `MQTT_HOST` from `.env`
— that value (`mosquitto`) is the in-container service name, unresolvable from the Mac
host. If you override the published port in `.env` (`MQTT_PORT`), pass
`HARNESS_MQTT_PORT=<port>` to the harness.

## 10. Supported media behavior

```text
Input file
   ↓
ffprobe
   ↓
decode test
   ↓
normalize if necessary
   ↓
test pipeline
```

We support any format the installed FFmpeg build can actually decode — determined by probing
and decoding it, never by trusting the filename extension.

**Common image formats**: JPG/JPEG, PNG, WEBP, BMP, GIF, TIFF, AVIF.
**Common video containers**: MP4, MOV, MKV, AVI, MPEG/MPG, WebM, M4V, TS/MTS.
**Common video codecs**: H.264, H.265/HEVC, VP8, VP9, AV1, MPEG-2, MPEG-4, MJPEG.

**HEIC/HEIF**: conditional support. Frigate's Face Library does not accept HEIC directly —
convert to JPEG/PNG first:
```bash
ffmpeg -i photo.heic photo.jpg
```

**Canonical normalized outputs** (what we standardize on if re-encoding):
images → JPEG or PNG; videos → MP4 with H.264; extracted frames → JPEG or PNG.

**Two distinct failure classes — never conflate them:**

| Result | Meaning |
|---|---|
| `MEDIA_DECODE_FAILURE` | The file itself couldn't be probed/decoded — a media problem, unrelated to whether a person is in it |
| `PERSON_NOT_DETECTED` | The file decoded fine; Frigate simply didn't find a person in it |

A corrupt or unsupported file must **never** be silently reported as "no person detected" —
that would hide a media problem behind a false negative.

## 11. Person-positive test

```text
video contains person
        ↓
Frigate sees person
        ↓
person event generated
```

1. Place a clip of a person walking toward the camera at
   `tests/phase1/test-media/known-person-walk.mp4` (per §9) and restart Frigate.
2. **Frigate UI**: open <http://localhost:5001>, select the `front_door` camera, and confirm
   you see live (looped) video with a detection box around the person.
3. **Frigate logs**:
   ```bash
   docker compose logs -f frigate | grep -i "front_door"
   ```
   Look for detection activity, not the "Unable to read frames" errors from §6.
4. **MQTT**: subscribe to Frigate's event topic and watch for a `person` label:
   ```bash
   mosquitto_sub -h localhost -p 1883 -t 'frigate/events' | python3 -m json.tool
   ```
   (Frigate publishes JSON on `new`/`update`/`end` events — see
   `specs/001-front-door-person-identification/contracts/mqtt-events.md` for the full
   payload shape this project relies on.)

## 12. Person-negative test

```text
video contains no person
        ↓
no person identity event
```

1. Provide a clip of ordinary motion with **no person** (e.g. a curtain moving, a car passing
   in the far background) as a separate test file, e.g.
   `tests/phase1/test-media/no-person-motion.mp4`.
2. Temporarily point `frigate/config/config.yml`'s go2rtc `exec:` producer at that filename
   instead (or swap the file at the `known-person-walk.mp4` path — either works, just be
   consistent about which you're testing), then `docker compose restart frigate`.
3. Confirm via the same MQTT subscription (§11 step 4) that **no** `person`-labeled event
   fires while this clip loops.
4. Revert the config/filename back afterward so you don't lose track of which clip is
   "current."

This proves ordinary motion doesn't become a false identity event — a Phase 1 form of spec
success criterion SC-002/SC-004.

## 13. Home Assistant test

The throwaway Home Assistant instance (<http://localhost:8124>) and Frigate share the same
isolated MQTT broker. As of T018/T026 the throwaway instance has an MQTT config entry pointed
at `mosquitto:1883` and a declared MQTT sensor (`sensor.frigate_events_test`, state topic
`frigate/events`), and it demonstrably updates to `person` when Frigate events fire.

To verify HA visibility yourself:
1. Log into <http://localhost:8124> (first run prompts you to create a local-only admin
   account — this account is disposable, matches nothing production).
2. Settings → Devices & Services → confirm an MQTT integration exists (add one pointed at
   `mosquitto:1883` if not already present, using the throwaway instance's own settings —
   never reuse production credentials here). Note: in HA 2024.x the broker host/port must be
   set via this config entry; top-level `mqtt: broker:`/`port:` YAML keys raise "Invalid
   config for 'mqtt'" (found during T018).
3. Developer Tools → States → filter for `frigate` or the configured camera name, and confirm
   an entity updates when a person event fires (§11).

> **Do not read the throwaway HA's SQLite database (`home-assistant_v2.db`) with the host
> `sqlite3` CLI while HA is running** — the macOS CLI (sqlite 3.43) reading HA's newer-format
> WAL can trigger HA's own corruption detector (observed during T026; HA auto-recovers by
> renaming the DB, but it's needless churn on a container you'd rather leave alone). Prefer
> the HA REST/WebSocket API for state checks.

**Do not modify your production Home Assistant to perform this test.** This section is about
the throwaway instance only.

## 14. Restarting later

```bash
docker compose stop
```

Safely stops all three containers without deleting anything — configs, Frigate's database,
and the throwaway HA's onboarding state all survive.

```bash
docker compose start
```

Resumes them exactly as they were.

**Do not run** `docker compose down -v` **as a routine command.** `-v` removes the named
volumes, which would destroy Frigate's database and the throwaway HA's configuration/state,
forcing you to redo onboarding and re-validate from scratch. Only ever run it deliberately,
and only when you actually want a full reset (see §15).

## 15. Cleanup

**Safe / non-destructive** (use freely):
```bash
docker compose stop              # stop containers, keep everything
docker compose ps -a              # confirm stopped state
```

**Destructive — clearly labeled, use only when you deliberately want a full reset:**
```bash
docker compose down               # removes containers (not volumes) — config on disk under
                                   # frigate/config/, home-assistant/throwaway-config/, and
                                   # mosquitto/config/ survives; container state doesn't
docker compose down -v            # DESTRUCTIVE: also removes named volumes — full reset
rm -rf home-assistant/throwaway-config/   # DESTRUCTIVE: wipes the throwaway HA's onboarding
rm -rf frigate/config/*.db*                # DESTRUCTIVE: wipes Frigate's own database
```
None of the destructive commands above touch `tests/phase1/test-media/` or any file tracked
in git — they only affect generated runtime state.

## 16. Troubleshooting

### Real problems already discovered in this project

**macOS AirPlay occupying port 5000**
- *Symptom*: `Error response from daemon: ports are not available: exposing port TCP
  0.0.0.0:5000 ... address already in use`
- *Cause*: macOS Control Center's AirPlay Receiver listens on 5000 by default (confirmed via
  `lsof -nP -iTCP:5000 -sTCP:LISTEN` → `ControlCenter`).
- *Solution*: Frigate's UI is mapped to host port **5001** instead (`.env.example`'s
  `FRIGATE_UI_PORT`) — already fixed in this repo's config, nothing to do unless you've
  changed the port mapping yourself.

**Frigate `/media` bind-mount collision**
- *Symptom*: Frigate crashes at startup with `OSError: [Errno 30] Read-only file system:
  '/media/frigate'`.
- *Cause*: an earlier `docker-compose.yml` mounted the read-only sample-media directory
  directly at `/media`, colliding with Frigate's own need to write `/media/frigate/...` for
  its clips/recordings/exports/database.
- *Solution*: sample media is mounted at `/media/test-source:ro` instead, leaving
  `/media/frigate` free — already fixed in this repo's `docker-compose.yml`.

**go2rtc `exec:` producer escaping — `{output}` vs `{{output}}`**
- *Symptom*: `[ERROR] Invalid substitution found` plus a Python-style `'output'` KeyError in
  Frigate's logs.
- *Cause*: Frigate applies its own `{}`-format pass over embedded go2rtc stream strings before
  handing them to go2rtc, so a single-brace `{output}` collides with Frigate's own templating.
- *Solution*: use the doubled form `{{output}}` — already fixed in
  `frigate/config/config.yml`.

**FFmpeg executable path inside the container**
- *Symptom*: `exec: "ffmpeg": executable file not found in $PATH`, specifically from go2rtc's
  `exec:` producer (Frigate's own capture process ffmpeg works fine — it resolves its binary
  differently).
- *Cause*: go2rtc's `exec:` producer runs with a minimal `PATH` that doesn't include Frigate's
  bundled ffmpeg build directories (`/usr/lib/ffmpeg/7.0/bin/`, `/usr/lib/ffmpeg/5.0/bin/`).
- *Solution*: reference the absolute path,
  `/usr/lib/ffmpeg/7.0/bin/ffmpeg` — already fixed in `frigate/config/config.yml`.

### Other problems you may hit

**Docker Desktop not running**
- *Symptom*: `Cannot connect to the Docker daemon at unix:///.../docker.sock. Is the docker
  daemon running?`
- *Solution*: `open -a Docker`, wait ~10-20s, retry. Confirm with `docker info`.

**MQTT connection refused / "Lookup error"**
- *Symptom*: `mosquitto_sub`/`mosquitto_pub` hang or error with "Connection refused" or
  "Unable to connect (Lookup error)".
- *Solution*: confirm the `mosquitto` container is running (`docker compose ps`) and that
  you're using port 1883 (or your `.env`'s `MQTT_PORT` override). If you see "Lookup error",
  you're probably using `MQTT_HOST=mosquitto` from `.env` — that hostname only resolves
  inside the compose network. From the Mac host, use `-h localhost`/`127.0.0.1` (the
  harness does this automatically; see §9a).

**Frigate restart loop**
- *Symptom*: `docker compose ps` shows `Restarting` repeatedly, or `RestartCount` climbing in
  `docker inspect`.
- *Solution*: check `docker compose logs frigate` for a Python traceback near the top of the
  log (a genuine config parse failure) — this is different from the expected per-camera
  ffmpeg retry described in §6, which does **not** restart the container itself.

**Test video not found**
- *Symptom*: repeated `Error opening input file rtsp://127.0.0.1:8554/front_door_test` /
  `Server returned 404 Not Found` in Frigate's logs.
- *Solution*: this is expected until you've completed T008 (§8/§9) — the go2rtc `exec:`
  producer can't loop a file that doesn't exist yet. Not a bug.

**Unsupported codec**
- *Symptom*: `scripts/loop-test-video.sh` reports `MEDIA_DECODE_FAILURE`.
- *Solution*: re-encode per §9 step 4 / §10's normalization guidance.

**Low disk space**
- *Symptom*: Docker pulls or Frigate writes fail with "no space left on device."
- *Solution*: this Mac had ~16 GB free at last check (`validation-report.md`, PD-01). Clear
  space (`docker system prune` — safe, only removes unused images/build cache, not this
  project's running containers or volumes) before adding more sample media or letting Frigate
  accumulate clips.

## 17. Current Phase 1 acceptance checklist

This is a **template** — check items off as you personally verify them on your Mac. The
authoritative, currently-recorded status is always
[validation-report.md](../../specs/001-front-door-person-identification/validation-report.md),
not this checklist.

- [x] containers running
- [x] Frigate UI reachable
- [x] throwaway HA reachable
- [x] MQTT round trip
- [x] sample media probes
- [x] person-positive sample passes (harness T020)
- [x] person-negative sample passes (harness T021)
- [x] identity-unavailable classification + recovery passes (harness T022)
- [x] Home Assistant event path passes
- [x] T019 validation report updated
- [x] T019 PASS (gate cleared)
- [x] T020-T026 person-detection MVP harness PASS (`run_harness.sh all` → OVERALL PASS)

**DO NOT START T027 UNTIL the Phase 3 checkpoint is confirmed PASS.**
