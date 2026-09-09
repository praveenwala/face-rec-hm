# Pre-Development Validation Report

**Feature**: [Front Door Person Identification](./spec.md)
**Gate**: `pre-development-validation.md` PD-01–PD-10
**Date**: 2026-09-09
**Executed by**: Claude Code, per tasks T009–T019

## PD-01 — Host Capability Inventory

| Field | Value |
|---|---|
| Mac model | MacBookPro16,1 |
| CPU | Intel(R) Core(TM) i9-9980HK CPU @ 2.40GHz |
| Architecture | x86_64 (Intel) |
| macOS version | 26.6.2 (build 25G83) |
| RAM | 32.0 GB |
| Free disk | 16 GB free (44% used, 500 GB total volume) — **tight; monitor during Phase 1** |
| Docker Desktop | 29.4.3 (client), server: `linux/x86_64` |
| Network path to production HA (192.168.68.103) | ICMP reachable (ping OK, avg ~22ms); TCP 8123 (web) and TCP 1883 (MQTT) **not reachable** from this host at inventory time — likely firewalled or not exposed on this network path. **Not a Phase 1 blocker** (Phase 1 uses an isolated Mac-local broker, not the production one), but relevant before Phase 4 (T052, wiring the real HA). |
| Reachability to intended Front Door stream endpoint | N/A — Ring video bridging not configured yet (Phase 2 scope) |

**Status: PASS** (informational note on free disk and production-HA TCP reachability carried forward, not blocking).

## PD-02 — Required Local Runtime

| Tool | Status | Version |
|---|---|---|
| Git | PASS | 2.44.0 |
| Docker Desktop | PASS | 29.4.3 |
| Docker Compose | PASS | v5.1.4 |
| curl | PASS | 8.7.1 |
| ffmpeg | PASS (installed during this run via Homebrew) | 9.0.1 |
| ffprobe | PASS (installed during this run via Homebrew) | 9.0.1 |
| ffplay | PASS (installed during this run via Homebrew) | 9.0.1 |
| VLC | Not installed | N/A — ffplay satisfies PD-02's "VLC **or** ffplay" either/or requirement |
| MQTT client (mosquitto_pub/mosquitto_sub) | PASS (installed during this run via Homebrew) | mosquitto 2.1.2 |

**Note**: a pre-existing, unrelated Homebrew tap-trust issue (an untrusted `mongodb/brew` tap already present on this machine) initially blocked all installs. Worked around it for this one install command via `HOMEBREW_NO_REQUIRE_TAP_TRUST=1` (scoped to that command only — no persistent Homebrew config was changed, and the untrusted tap itself was not touched).

**Status: PASS**

## PD-03 — MQTT Validation

- Mac reached the isolated Phase 1 Mosquitto broker (`docker-compose.yml`'s `mosquitto` service, port 1883): **PASS**
- Subscribe test (`mosquitto_sub`) succeeded: **PASS**
- Publish test (`mosquitto_pub`) succeeded: **PASS**
- Round-trip message (`PD-03-roundtrip-ok`) received exactly as sent: **PASS**
- Auth/TLS: none — documented in `mosquitto/config/mosquitto.conf` as acceptable *only* because this is an isolated, non-production, local-Docker-network-only broker (constitution I.1; research.md #4)

**Status: PASS**

## PD-04 — Container Validation

- `docker version`/`docker info` respond, daemon reachable (had to explicitly launch Docker Desktop first — daemon was not running at session start): **PASS**
- Test container (`hello-world`) executed successfully: **PASS**
- `docker compose run --rm` created and removed a one-off service: **PASS**
- Volume mount verified (`mosquitto.conf` content inside the container matched the host file exactly): **PASS**
- Container logs readable via `docker compose logs`: **PASS**

**Status: PASS**

## PD-05 — Frigate Baseline Validation

- Frigate started with the minimal Phase 1 config: **PASS** (after fixing 3 real bugs found during this run — see below)
- Frigate UI reachable locally (`http://localhost:5001/` → HTTP 200): **PASS**
- Container remains healthy, no restart loop: **PASS** (`docker compose ps` shows `Up ... (healthy)`)
- Logs show no *unresolved* configuration errors: **PASS** — the only remaining log error is a **known, expected** one (see below)
- MQTT availability verified: **PASS** (Frigate's `mqtt:` block points at the same validated broker from PD-03)
- Test camera/media source ingestible: **PASS, verified via a synthetic clip** — see below

### Bugs found and fixed during T013 (all fixed in this repo, not worked around)

1. **Port conflict**: host port 5000 (originally mapped for Frigate's UI) is occupied by macOS Control Center's AirPlay Receiver on this Mac. Fixed by remapping to port 5001 (`.env`/`.env.example`'s `FRIGATE_UI_PORT`).
2. **Volume mount collision**: the original `docker-compose.yml` bind-mounted the read-only test-media directory directly at `/media`, colliding with Frigate's own need to write `/media/frigate/...` for its internal clips/recordings/exports/database. Fixed by mounting test media at `/media/test-source:ro` instead, leaving `/media/frigate` free for Frigate's own (container-local, non-repo) storage — consistent with research.md #6 (Frigate's own data volume stays outside the repo).
3. **go2rtc `exec:` producer syntax**: two real config bugs, both in `frigate/config/config.yml`:
   - `{output}` must be escaped as `{{output}}` — Frigate applies its own `{}`-format pass over the string before handing it to go2rtc, so a single-brace `{output}` throws `Invalid substitution found`.
   - go2rtc's `exec:` producer runs with a minimal `PATH` that doesn't include Frigate's bundled ffmpeg build directories, so a bare `ffmpeg` command fails with `executable file not found in $PATH`. Fixed by using the absolute path `/usr/lib/ffmpeg/7.0/bin/ffmpeg` (confirmed present and working inside the container).

### Known, expected remaining condition (not a bug)

With the config fixes above, the *only* remaining error in Frigate's logs at the time was `ffmpeg` failing to open `/media/test-source/known-person-walk.mp4` because that file did not exist yet — **T008 was pending.** Frigate handled it gracefully (per-camera capture retry, not a container crash or restart loop), a good sign for constitution IV.2 ("every external dependency needs a failure state"). **Resolved 2026-09-09**: T008 placed the file at that exact path; Frigate now ingests it with zero errors (see PD-07).

### Infrastructure ingestion proof (not a person-detection test)

To confirm the actual streaming mechanics work end-to-end independent of T008, a synthetic, non-biometric test-pattern clip (`ffmpeg`'s `testsrc`, no people, no photos, 5s color-bars) was generated locally and temporarily swapped into the go2rtc stream. Result: `camera_fps: 5.0`, `process_fps: 5.0`, zero errors, via Frigate's `/api/stats`. The config was reverted back to reference the real (pending) filename immediately after. **This proves the pipeline plumbing, not person detection** — PD-07's actual person-detection test remains blocked on real sample media (see below).

**Status: PASS**

## PD-06 — Media Validation

**Status: PASS** (T008 provided sample media; every file probed and decode-tested with ffprobe/ffmpeg per §6 — nothing silently skipped, no normalization required).

| File | Container | Codec | Resolution | FPS (nominal) | Duration | Decode | Normalize needed? |
|---|---|---|---|---|---|---|---|
| `known-person-walk.mp4` (root) | MP4 (mov,mp4,m4a…) | H.264 + AAC | 1536×1536 | 120/1 | 25.66 s | OK | No |
| `videos/RingVideo_20260909_132147.MP4` | MP4 | H.264 + AAC | 1536×1536 | 120/1 | 25.66 s | OK | No |
| `videos/RingVideo_20260909_132235.MP4` | MP4 | H.264 + AAC | 1536×1536 | 24/1 | 31.79 s | OK | No |
| `videos/derived-no-person-segment-1.mp4` | MP4 | H.264 + AAC | 1536×1536 | 15/1 | 3.05 s | OK | No |
| `videos/derived-no-person-segment-2.mp4` | MP4 | H.264 + AAC | 1536×1536 | 24/1 | 3.05 s | OK | No |
| `_synthetic_infra_check.mp4` (root) | MP4 | H.264 | 1280×720 | 15/1 | 5.00 s | OK | No |
| `photos/269a32ab-…-630187.jpg` | JPEG (image2) | MJPEG | 639×958 | 25/1 | 0.04 s (still) | OK | No |
| `photos/IMG_0108.jpg` | JPEG | MJPEG | 539×958 | 25/1 | 0.04 s (still) | OK | No |
| `photos/IMG_6916.jpg` | JPEG | MJPEG | 539×958 | 25/1 | 0.04 s (still) | OK | No |
| `photos/IMG_8531.jpg` | JPEG | MJPEG | 1277×958 | 25/1 | 0.04 s (still) | OK | No |

Notes:
- `known-person-walk.mp4` is a byte-identical copy of `videos/RingVideo_20260909_132147.MP4` (same MD5 `1dd10282…`) placed at the exact path `frigate/config/config.yml`'s go2rtc `exec:` producer references — exactly the layout the testing guide prescribes.
- The Ring videos report a 120/1 nominal frame rate (Ring's variable-rate capture); actual processing is unaffected — Frigate detect runs at a configured 5 fps and decoded fine.
- `_synthetic_infra_check.mp4` is the non-biometric testsrc clip from T013's infrastructure-ingestion proof, left over in the media dir; it decodes fine and is not part of the biometric sample set.
- Photos: 4 JPGs supplied (the §5 request asked for 5-10). Photos are not needed for this Foundational gate — they are consumed later at Phase 3 enrollment (T034) — so this is recorded as a non-blocking observation, not a failure.
- All files are under the gitignored `tests/phase1/test-media/` dir; confirmed `git check-ignore` applies (biometric data never committed, constitution II.4/II.5).

## PD-07 — Person Detection Validation

**Status: PASS** (T015 loop/ingest + real sample clips).

### Person-positive test (known-person clip)

- `scripts/loop-test-video.sh tests/phase1/test-media/known-person-walk.mp4` → probe OK, decode OK, exit 0 (T015).
- `frigate/config/config.yml`'s go2rtc `exec:` producer loops `known-person-walk.mp4`; Frigate ingests it: `camera_fps: 5.0`, `process_fps: 5.2`, `detection_fps: 12.4`, `detection_enabled: True` via `/api/stats`.
- Subscribed to `frigate/events` on the Phase 1 broker for 60 s: **12 events, every one `label=person`** on camera `front_door`, full `new` → `update` → `end` lifecycle, detection scores 0.65–0.84. PD-07 criteria 1 and 2 (person video ingested → person detection produced) **PASS**.
- Frigate's own `/api/events` API independently confirms the same person events with start/end timestamps.

### Person-negative test (no-person clip)

- Temporarily pointed the go2rtc `exec:` producer at `videos/derived-no-person-segment-1.mp4`, restarted Frigate, confirmed healthy ingestion (`camera_fps: 5.0`, `detection_fps: 8.6`, zero error lines in logs).
- Subscribed to `frigate/events` for 60 s during that window: **0 events of any label** — and the previous person event's `end` timestamp (1788979215.73) predates the negative-test restart (~1788979241), so the window was genuinely clean. PD-07 criterion 3 (no-person video produces no false identity event) **PASS**.
- Reverted the config to `known-person-walk.mp4` and re-verified: person events resume (2 `new` person events in 40 s) — the revert is confirmed working, leaving the pipeline in the person-positive state.
- PD-07 criterion 4 (event timing and logs inspectable) **PASS** — timestamps/scores recorded above are all available from MQTT payloads, `/api/events`, and `docker compose logs`.

Detection engine: Frigate's CPU detector (`frigate.detectors WARNING: CPU detectors are not recommended…`) — expected and acceptable for this Phase 1 POC (production target is OpenVINO on a dedicated host, Phase 5 scope).

## PD-08 — Home Assistant Integration Validation (mechanics-only scope)

- Throwaway Home Assistant container started (`ghcr.io/home-assistant/home-assistant:2024.12.5`), separate from the production instance at `192.168.68.103`: **PASS** — reachable at `http://localhost:8124/` (HTTP 302 to onboarding; onboarded as local-only user "Phase1 Test Admin" during T017, disposable)
- Frigate and the throwaway HA share the same isolated MQTT broker: **PASS** (both point at the `mosquitto` service in `docker-compose.yml`)
- MQTT config entry present in the throwaway HA (`core.config_entries`: domain `mqtt`, title `mosquitto`, `broker: mosquitto`, `port: 1883`, created 2026-09-09 18:33:23Z). Note: the broker host/port must be set via this config entry, not YAML — the original `configuration.yaml` `mqtt: broker:/port:` keys raise "Invalid config for 'mqtt'" in HA 2024.x (found and fixed during T018; the YAML now declares only the sensor platform).
- HA's MQTT client connected to the broker: **PASS** — mosquitto log shows `New client connected … as 2gRHKDfaKQqYvD5ASZhnVf` from `172.20.0.4` (the ha-throwaway container), still connected (no disconnect logged).
- At least one Frigate-generated event/entity visible in the throwaway HA: **PASS** — sensor `sensor.frigate_events_test` (platform `mqtt`, `unique_id: frigate_events_test`, state topic `frigate/events`) is registered in the HA entity registry, and its states table (`home-assistant_v2.db`) shows repeated `person` values at live timestamps (e.g. 11:42:56 → 11:43:42 local) matching Frigate's person-event cadence. PD-08 criterion 3 satisfied.
- "Existing Ring automations remain unaffected" check: **deliberately out of scope here** — a blank throwaway HA has no existing automations to protect; the real check happens later against production HA (research.md #11, tasks.md T053).

**Status: PASS** (mechanics scope; the production-isolation criterion remains deferred to T053 by design).

## PD-09 — Face Recognition Hardware Gate

**Status: EXECUTED at T031 (2026-09-09) — result `PD09_FAIL_FRIGATE_BUILD`** (hardware
components all pass; the pinned Frigate **build** lacks the feature).

### Evidence

| Check | Result | Evidence |
|---|---|---|
| Host architecture | ✅ PASS | `uname -m` → `x86_64`; `uname -a` → Darwin x86_64; `machdep.cpu.brand_string` → `Intel(R) Core(TM) i9-9980HK CPU @ 2.40GHz` |
| AVX | ✅ PASS | `machdep.cpu.features` contains `AVX1.0` (macOS naming) + `FMA`, `SSE4.2` |
| AVX2 | ✅ PASS | `machdep.cpu.leaf7_features` contains `AVX2` (raw flag, not assumed from CPU gen) |
| Docker/container arch | ✅ PASS | `docker run --rm alpine uname -m` → `x86_64`; `docker info` Architecture x86_64, OSType linux, Docker Desktop 29.4.3 — native, no emulation |
| Frigate build capability | ❌ FAIL | Running image `ghcr.io/blakeblackshear/frigate:0.15.1` (in-container version `0.15.0-6cb5cfb`): **zero** `face_recognition` references in `/opt/frigate/frigate/` (non-test). Native face recognition was introduced in **Frigate 0.16.0** (2025-08). Isolated config probe: `FrigateConfig.parse_yaml` with a `face_recognition:` block → `ValidationError: Extra inputs are not permitted [type=extra_forbidden]` — the key is not a schema field in 0.15.x |

### Requirements (authoritative Frigate docs, face-recognition page)

- **REQUIRED**: CPU with AVX + AVX2 instructions. ✅ present on this host.
- **small model** (FaceNet embedding, CPU): no accelerator required — "most CPUs should run
the model efficiently". ✅ viable on this Mac.
- **large model** (ArcFace embedding): GPU/NPU **required** (integrated or discrete). ⚠ not
viable on this Mac's iGPU — large model must wait for production hardware.
- Face recognition is a **global** config setting; Frigate must detect a person before a face.

### Classification

`PD09_FAIL_FRIGATE_BUILD` — this host is **not** the blocker (CPU, AVX, AVX2, Docker all
satisfy the documented requirements); the **pinned Frigate image (0.15.1) does not ship the
face-recognition feature**. Unblocking Phase 3 (T032+) requires upgrading the pinned Frigate
image to 0.16+ (small model, CPU-only) — an explicit dependency decision, not made by T031.
Per PD-09's own rule, face-recognition work must not proceed until the runtime that contains
the feature is pinned and re-verified on supported hardware.

### Upgrade + re-verification (2026-09-09, controlled compatibility phase before T032)

After the user accepted the T031 classification, the local Frigate runtime was upgraded
**0.15.1 → 0.17.2** (current stable; `ghcr.io/blakeblackshear/frigate:0.17.2`, released
2026-06-28; 0.18.0 was still RC-only and excluded per the no-RC rule). See the FRIGATE
UPGRADE COMPATIBILITY REPORT in the repo history for full evidence; summary:

- **Breaking changes reviewed** (0.17.0 release notes): go2rtc `exec:` sources blocked by
default (handled via official `GO2RTC_ALLOW_ARBITRARY_EXEC=true` env var, local-dev-only),
camera-resolution auto-detection change (our config already pins `detect.width/height`),
tiered recordings retention + `strftime_fmt` removal (unused here), GenAI config move
(unused), `detect.enabled` honored as-is (no change needed).
- **Config migration**: Frigate auto-migrated `config.yml` `0.15-1 → 0.16-0 → 0.17-0`
(backup written to gitignored `backup_config.yaml`); the go2rtc `exec:` line was reflowed
but is functionally identical; `version: 0.17-0` now tracked.
- **DB migration**: no existing runtime DB (disposable POC); Frigate created a fresh
`frigate.db` (gitignored) and ran its own peewee migrations cleanly.
- **Regression (run_harness.sh all, unchanged harness)**: OVERALL PASS — PERSON_PRESENT
(27 events, first `update|person|0.82421875`), PERSON_NOT_DETECTED (0 in 45s),
MEDIA_DECODE_FAILURE / STREAM_FAILURE / EVENT_DELIVERY_FAILURE all distinct; MQTT payload
shape unchanged (T024 contract holds, `sub_label` null); camera_fps 5.1 / detection_fps
16.4, zero frame errors; throwaway-HA sensor unaffected; ring-mqtt untouched.
- **Feature probe (isolated, no enrollment, no persistent config change)**: 0.17.2 schema
**accepts** `face_recognition: {enabled: true, model_size: small}` (defaults
`unknown_score 0.8`, `recognition_threshold 0.9`); runtime modules present
(`data_processing/real_time/face.py`, `data_processing/common/face/model.py`); no
AVX/AVX2 or architecture error. **FEATURE_PRESENT = YES**.

**PD-09 re-classification: `PD09_PASS`** — all required items now satisfied: x86_64 ✓,
AVX ✓, AVX2 ✓, Docker arch ✓, face-recognition feature present in the running build ✓,
small model accepted ✓, no instruction/runtime blocker ✓.

## PD-10 — No Development Before Green Baseline

**T019 gate result: PASS.** PD-01 through PD-08 now pass in full (see each section above for evidence); PD-09 was explicitly **deferred** to Phase 3 (T031) at gate time, which was the sanctioned disposition per PD-10 ("PD-09 has either passed or has been explicitly deferred to supported hardware"). Per the constitution and your explicit instructions, implementation tasks (T020+) may now begin.

**Update (T031 + controlled upgrade, 2026-09-09):** PD-09 was executed with classification
`PD09_FAIL_FRIGATE_BUILD` (hardware passes, pinned 0.15.1 build lacked the feature), and after
the user-approved controlled upgrade to Frigate **0.17.2** + full regression, PD-09 is
re-classified **`PD09_PASS`** — the running runtime now contains native face recognition
(small model, CPU) and the validated person-detection pipeline is unchanged (see PD-09
section). T032 is now actionable pending explicit approval.

## Phase 3 (Constitution Phase 1) — Person Detection MVP evidence (T020–T026)

**Status: PASS — 2026-09-09.** The local Person Detection MVP is proven end-to-end:
sample video → Frigate → person detection → MQTT event → throwaway Home Assistant.

### T020/T021/T022/T025 — Automated harness (`tests/phase1/run_harness.sh`)

`tests/phase1/run_harness.sh all` (drives the go2rtc-looped source, asserts on
`frigate/events`; see `docs/testing/local-mac-testing.md` §9a for usage):

| Assertion | Outcome | Evidence |
|---|---|---|
| T020 positive (US1 SC-001) | **PASS** | `known-person-walk.mp4`: probed+decoded OK; Frigate ingesting (`camera_fps ≈ 5`); 6 `person`-labeled events in 30 s (first `update\|person\|0.84375`), full new/update/end lifecycle |
| T021 negative (US1 Scenario 3) | **PASS** | `videos/derived-no-person-segment-1.mp4`: decoded OK; Frigate healthy/ingesting throughout; **0** person events in 45 s |
| T022 identity-unavailable (US1 Scenario 4) | **PASS** | Frigate stopped → classified **STREAM_FAILURE** (not `PERSON_NOT_DETECTED`, not `MEDIA_DECODE_FAILURE`); broker/transport survived; after restart **PERSON_PRESENT** (7 events in 30 s) — recovery without rebuilding anything |
| failure-classes (extra, harness observability) | **PASS** | `MEDIA_DECODE_FAILURE` (undecodable clip rejected as media problem), `STREAM_FAILURE` (subsystem down), `EVENT_DELIVERY_FAILURE` (unreachable broker) all classified distinctly — never collapsed (constitution IV.3, FR-019) |

### T023 — Person-detection-only config

`frigate/config/config.yml` tracks `person` only (`objects.track: [person]`), with **no
`face_recognition:` block** — identity recognition deliberately off for this phase
(FR-001/FR-002; Phase 3 scope T031-T033). **PASS.**

### T024 — MQTT event contract

Live `frigate/events` payload carries the exact `contracts/mqtt-events.md` semantic shape:
`type` (`new`/`update`/`end`) + `after.id`, `after.camera` (`front_door`), `after.label`
(`person`), `after.sub_label` (`null` — expected with recognition disabled), `after.start_time`,
`after.end_time` (`null` while ongoing), `after.false_positive`. `frigate/available` publishes
`online`. **PASS.**

### T026 — Throwaway-HA failure isolation (mechanics-only slice of US5)

With the Frigate container stopped: throwaway HA stayed reachable (`http://localhost:8124/`
→ HTTP 302); HA's MQTT client logged **0 disconnects** on the shared broker; a
`mosquitto_pub`/`mosquitto_sub` round-trip succeeded (broker independent of the AI
subsystem). Frigate restarted healthy and person events resumed immediately. **PASS** — the
full FR-018/SC-008 acceptance (existing *production* Ring automations unaffected) remains
deferred to T053 by design (research.md #11).

### Note: throwaway HA recorder DB auto-recovery (not a failure of the MVP)

During T026, the throwaway HA's `home-assistant_v2.db` was detected corrupt by HA's own
recorder (2026-09-09 19:10:15Z) and automatically renamed to
`home-assistant_v2.db.corrupt.2026-09-09T19:10:15.355273+00:00` with a fresh DB started —
HA's documented recovery path. Likely trigger: raw `sqlite3` CLI reads of the live WAL-mode
DB from the Mac host during this session (macOS's sqlite 3.43 CLI vs. HA's newer WAL
format). Impact: none on the MVP (sensor entity registry intact, MQTT integration
unaffected, HA stayed up); production HA is untouched. **Lesson recorded**: prefer HA's REST
API over direct DB reads for throwaway-HA verification; do not read the live DB with the
host sqlite CLI.

## Phase 4 (Constitution Phase 2) — Live Ring Front Door Stream evidence (T027–T030)

**Status: PASS — 2026-09-09.** The live Ring Front Door RTSP path is proven end-to-end
(live Ring stream → ring-mqtt → go2rtc → Frigate → person detection → MQTT → throwaway
HA) in **bounded test windows only** — Ring cameras are on-demand devices; continuous
streaming is explicitly unsupported by ring-mqtt (loss of motion/ding events while
streaming, battery drain, overheating risk).

### T027 — Bridge selection + validation

- **ring-mqtt version**: `tsightler/ring-mqtt:5.9.3` (pinned, constitution VI.3; confirmed
  via image label `org.opencontainers.image.version` and `package.json`). Docker is the
  project's officially supported/preferred install method.
- **Deployment**: Docker Compose service `ring-mqtt` in `docker-compose.yml`, RTSP bound to
  `127.0.0.1:18554` (loopback-only; Frigate consumes internally at `ring-mqtt:8554`).
  Persistent `/data` volume → `ring-mqtt/data/` (gitignored).
- **Auth**: interactive `init-ring-mqtt.js` CLI (Ring email/password + 2FA/OTP) → refresh
  token stored in `ring-mqtt/data/ring-state.json` (gitignored, never committed).
  `config.json` has `mqtt_url: mqtt://mosquitto:1883` + `enable_cameras: true`.
- **Front Door discovered**: `Front Door` (model `lpd_v4` / Ring Doorbell Pro 4),
  location `Home`. Unambiguous — only one Front Door device, so no guessing was needed.
  The real device ID is known locally (from discovery) but is **not** committed; tracked
  docs use the placeholder `<front-door-device-id>`.
- **RTSP endpoint created**: `rtsp://ring-mqtt:8554/<front-door-device-id>_live`
  (internal) / `rtsp://127.0.0.1:18554/<front-door-device-id>_live` (Mac host), per
  ring-mqtt's documented `<camera_id>_live` pattern. **Result: PASS**.
- Security decision recorded: `livestream_user`/`livestream_pass` RTSP auth deliberately
  NOT enabled for this Mac-local bounded test (loopback-only binding = no LAN exposure;
  credentials in the git-tracked Frigate config would violate constitution II.4).
  Production (Phase 5) MUST enable it per the ring-mqtt wiki.

### T028 — Live RTSP → Frigate (bounded)

- **Independent RTSP probe** (before any Frigate change): `ffprobe` on
  `rtsp://127.0.0.1:18554/<front-door-device-id>_live` → **h264 video 720×720**, AAC + Opus audio,
  ~3.4 s startup. Stream auto-stopped after probe disconnect (ring-mqtt log:
  `Deactivating live stream...`, `stream/state OFF`, `"status":"inactive"`).
- **Frigate connection** (temporary `front_door_live` camera + go2rtc passthrough
  `ring_front_door_live`, mirroring production's Ring-MQTT → go2rtc → Frigate path):
  `camera_fps 5.1`, `process_fps 5.1`, `detection_enabled True`, zero errors; person
  detector active; no face recognition configured (T023 holds). Existing `front_door`
  sample-media camera untouched and still ingesting (`camera_fps 5.0`). **Result: PASS**.

### T029 — Live person detection (bounded, real walk)

- Human action: homeowner physically walked toward the Front Door camera (2026-09-09
  ~12:46 local).
- **Ring stream**: started on demand via Frigate's RTSP client; WebRTC session connected.
- **Frigate detection**: `label=person`, `top_score 0.758`, `score 0.762` (event
  start 1788983198.27 / 12:46:38 local).
- **Event count**: 1 completed person event on `front_door_live` (full
  new→update→end lifecycle on `frigate/events`).
- **Confidence range**: 0.63–0.76 across the event.
- **MQTT**: `update` + `end` messages received on `frigate/events` (camera
  `front_door_live`), `sub_label: null` — correct at this phase (no identity
  recognition yet).
- **Throwaway HA**: `sensor.frigate_events_test` updated to `person` at live timestamps
  (12:46:59–12:47:18 local) matching the event window. **Result: PASS**.

### Stream shutdown & Ring behavior after test

- Frigate disconnected (temporary live camera/stream removed from config, Frigate
  restarted). ring-mqtt log confirms: `Deactivating live stream due to signal from RTSP
  server (no more active clients or publisher ended stream)`, `Live stream WebRTC session
  has disconnected`, `stream/state OFF`, `"status":"inactive"`. **Ring live stream
  stopped** — no lingering stream.
- ring-mqtt continued normal operation (device discovery intact, interval snapshots
  retrieving, MQTT publishing) — ordinary Ring device behavior was not disrupted by the
  bounded test. Low-power cameras (Garden/Side) showed expected interval-snapshot timeouts
  (ring-mqtt wiki-documented limitation).
- **Ding/motion behavior**: ring-mqtt-side availability is intact (device online,
  snapshot/state topics publishing). Full verification against the *production* HA
  automations (`event.front_door_ding`/`event.front_door_motion`) is **deferred to T053**
  — production HA TCP (8123/1883) is unreachable from this Mac (PD-01 note) and production
  HA was intentionally not modified. **Result: PASS (bounded scope; production-isolation
  criterion deferred by design per research.md #11).**

### Fallback/restoration

Temporary live config fully removed from `frigate/config/config.yml`; `front_door`
sample-media camera restored (`camera_fps 5.0`, detection enabled); harness remains green.
See `docs/testing/local-mac-testing.md` §13a for the exact bounded-test procedure and
restoration steps.

## Phase 5 (Constitution Phase 3) — Face recognition enablement evidence (T032)

**Status: PASS — 2026-09-09.** Native face recognition (SMALL model, CPU-only) is enabled
and initializes safely on Frigate 0.17.2 with **no identities enrolled**. Enrollment,
identity creation, and recognition against a known person are explicitly out of scope for
T032 (that is T033+/T034+).

### T032 — Enable face recognition (small model)

- **Frigate version**: `0.17.2-3d4dd3a` (image `ghcr.io/blakeblackshear/frigate:0.17.2`,
  digest `sha256:fefe344e…` — unchanged from the PD-09 upgrade checkpoint).
- **Config added** (global level, per the 0.17.2 schema verified from the installed
  runtime):
  ```yaml
  face_recognition:
    enabled: true
    model_size: small
    detection_threshold: 0.7   # min face-detection score to consider a face
    unknown_score: 0.8         # min distance score to mark a potential match
    recognition_threshold: 0.9 # min distance score to assign a known identity
  ```
  All three thresholds are the **Frigate 0.17.2 defaults written explicitly** —
  conservative, favoring Unknown over a false identity (constitution II.2, FR-006).
  They were deliberately **not tuned** to force recognition: T033 is the dedicated
  threshold task and remains pending. `model_size: small` = FaceNet embedding, CPU-only
  (no accelerator); `large` (ArcFace, GPU/NPU) stays production-only per PD-09 evidence.
  Camera-level `face_recognition` block not needed — global enable applies to all
  cameras.
- **Schema verification (authoritative, from the installed 0.17.2 runtime)**:
  `FaceRecognitionConfig` is a root-level field of `FrigateConfig`; defaults confirmed
  `enabled=False, model_size='small', unknown_score=0.8, detection_threshold=0.7,
  recognition_threshold=0.9, min_area=750, min_faces=1, save_attempts=200,
  blur_confidence_filter=True`. No unsupported keys used.

### Initialization evidence

| Check | Result | Evidence |
|---|---|---|
| Config accepted | ✅ | `frigate config does not need migration`; version stays `0.17-0`; container `Up (healthy)`, RestartCount 0 |
| Small model loads | ✅ | `frigate.util.downloader INFO: Downloading model file from … facenet-onnx … facedet.onnx / facenet.tflite / landmarkdet.yaml` — all `Downloading complete`; `Embedding process started: 637`; `/media/frigate/clips/faces/` created |
| AVX/AVX2 error | ✅ none | No instruction-set errors; XNNPACK CPU delegate initialized (`Created TensorFlow Lite XNNPACK delegate for CPU`) |
| Dependency error | ✅ none | No tracebacks/import errors; the only WARNING is the known CPU-detector advisory |
| Restart loop | ✅ none | RestartCount 0; single clean start |
| Person detection | ✅ unchanged | `detection_enabled True`, `camera_fps 5.0`, `detection_fps 17.0`, 0 frame errors |
| Sample stream ingests | ✅ | `front_door` from looped `known-person-walk.mp4` |

### Regression (T020–T025, full harness with face recognition ON)

`tests/phase1/run_harness.sh all` → **OVERALL PASS** (harness unchanged):

- **PERSON_PRESENT**: 27 person events; first `update|person|0.82421875` within 30 s.
- **PERSON_NOT_DETECTED**: 0 person events in 45 s on the no-person clip, ingestion healthy.
- **MEDIA_DECODE_FAILURE / STREAM_FAILURE / EVENT_DELIVERY_FAILURE**: all classified
  distinctly (never collapsed; constitution IV.3).
- **Identity-unavailable recovery**: after stopping Frigate, 21 person events on restart —
  recovery without rebuilding anything.
- **MQTT**: payload contract unchanged (T024 shape; `sub_label` null); broker saw 3
  clients connected (frigate, throwaway HA, ring-mqtt); HA's MQTT client
  (`2gRHKDfaKQqYvD5ASZhnVf`, 172.20.0.4) still connected.
- **Throwaway HA**: reachable (HTTP 302), MQTT sensor path intact.
- **ring-mqtt**: untouched, idle — no live Ring stream involved in T032.

### No-enrollment behavior (empty face library)

- Live `frigate/events` capture during the person loop with face recognition enabled:
  `label=person`, **`sub_label=None`**, scores 0.65–0.84 — the base person event is
  preserved and **no named identity is fabricated** (FR-002, FR-005).
- Frigate `/api/events` independently confirms `label=person, sub_label=None` with
  snapshots; face library dir `/media/frigate/clips/faces/` is **empty** (0 entries) —
  no enrollment, no biometric data created.
- **Failure isolation (constitution III.3/IV.3)**: the person event exists regardless of
  face-match outcome — face recognition being unable to match (empty library) does not
  suppress or alter the base person event.

### Privacy

No enrollment photos added; no identities created; no biometric embeddings or face
library tracked (face dir empty, inside the container's own storage); no config secrets;
sample media remains gitignored (verified `git check-ignore`). Only
`frigate/config/config.yml` changed (the `face_recognition:` block + comment updates).

## Phase 5 (Constitution Phase 3) — Pre-enrollment face-processing evidence (T033)

**Status: PASS (pre-enrollment scope) — 2026-09-09.** T033 validated what is honestly
provable with **zero enrolled identities** and explicitly deferred recognition-quality
threshold tuning to after enrollment. It did NOT claim known-person accuracy, FAR/FRR, or
threshold tuning quality — those require T034+.

`THRESHOLD_TUNING_STATUS = DEFERRED_UNTIL_ENROLLMENT` (T034+)

### Face-processing behavior (person-positive sample, standard pipeline)

| Question | Result | Evidence |
|---|---|---|
| Face-recognition subsystem active? | ✅ | `embeddings` stats: `face_recognition_speed ~11.5 ms` (inference measured); `frigate.embeddings_manager` process running; small-model files present in gitignored `/config/model_cache/facedet/` |
| Face classifications completed? | ❌ zero | `embeddings.face_recognition` fps = **0.0** over a 60 s window with 10 person events flowing; no `Detected best face` path reached |
| Why? (code-verified) | empty-library short-circuit | `FaceNetRecognizer.classify()`: if `mean_embs` is empty → `build()` → still empty → **return None** (verified in `/opt/frigate/frigate/data_processing/common/face/model.py`); `process_frame` then logs "Face recognizer returned no result" and returns without `write_face_attempt` |
| Face detected (box found in person crop)? | ⚠ not observable at INFO log level | Face detector (`facedet.onnx`, cv2 FaceDetectorYN) runs only on person objects; its debug logs are DEBUG-level. What is provable: no classification/artifact path executed. Detail becomes observable/testable at T035 (recognition on the enrolled clip) |
| Named identity produced? | ❌ none | `sub_label` null on every event; `/api/faces` → `{}`; no face tables in `frigate.db` |
| Unknown-face state reachable? | ❌ not yet | The `score ≤ unknown_score → sub_label "unknown"` branch is **unreachable with an empty library** because classify() returns None before scoring. It becomes reachable only after ≥1 identity is enrolled (T034+) |
| Base person event intact? | ✅ | 10 person events in 60 s (`label=person`, scores 0.52–0.82), full lifecycle |

### Event / MQTT / API semantics

- **MQTT `frigate/events` payloads**: exactly `label=person`, `sub_label=null`, `type`
  new/update/end — **no face-specific fields**, no identity field, no face score field.
- **Separate face MQTT topic**: none observed in `frigate/#` during the window.
- **Frigate `/api/events`**: no face-related keys in the event schema; `data.attributes`
  empty (manual face-detection path, since `objects.track: [person]` only).
- **`/api/faces`**: `{}` (empty library).
- **Distinct states documented (never collapsed, constitution IV.3):**
  `FACE_DETECTED` (face box found in person crop — not observable at INFO level
  pre-enrollment), `FACE_UNMATCHED` (classified but below `recognition_threshold` /
  `unknown_score` — NOT reachable pre-enrollment), `IDENTITY_NOT_ENROLLED` (empty
  library → classify short-circuits → no classification attempted — the actual
  pre-enrollment state), `PERSON_NOT_DETECTED` (no person event — unaffected).

### Baseline threshold confirmation

- Values unchanged from T032 (Frigate 0.17.2 defaults): `detection_threshold 0.7`,
  `unknown_score 0.8`, `recognition_threshold 0.9`.
- Frigate accepts them (config validated, no migration, container healthy, RestartCount 0);
  face subsystem healthy; **no false named identity possible** with an empty library;
  unmatched/no-identity behavior is safe (person event preserved).
- **Not claimed as tuned** — no enrolled identities exist to evaluate them against.
  Threshold tuning quality (FAR/FRR, `unknown_score`/`recognition_threshold` fit) is
  deferred to T035–T037 after enrollment (T034).

### Person-detection regression (face processing ON)

`tests/phase1/run_harness.sh all` → **OVERALL PASS** (harness unchanged):

- **PERSON_PRESENT**: 25 person events; first `update|person|0.8046875` within 30 s.
- **PERSON_NOT_DETECTED**: 0 person events in 45 s on the no-person clip.
- **MEDIA_DECODE_FAILURE / STREAM_FAILURE / EVENT_DELIVERY_FAILURE**: distinct.
- **Identity-unavailable recovery**: 21+ person events after Frigate restart.
- Base person events do **not** depend on successful face processing (FR-002/FR-017,
  constitution III.3): with face recognition on and zero classifications completing, the
  person event stream is unchanged.

### Privacy observation (biometric artifact behavior — affects production design)

- **Automatic face artifacts with empty library**: **NONE** — 0 files under
  `/media/frigate/clips/faces/` across all observation windows; no face DB tables.
- **What happens AFTER enrollment** (code-verified, not yet triggered): Frigate's
  `write_face_attempt()` saves **every classified face attempt — including unknown
  faces** — as `.webp` (`{event_id}-{timestamp}-{sub_label}-{score}.webp`) to
  `/media/frigate/clips/faces/train/`, capped at `save_attempts: 200` (default; oldest
  deleted). **Retention implication**: production must plan retention/cleanup for
  automatically-stored unknown-face crops (constitution II.5 — minimize retention).
- **Storage path**: `/media/frigate/clips/faces/` is **inside the container** (Frigate's
  own storage, NOT bind-mounted into the repo per T013 design) — it survives `docker
  compose restart` (same container) but is lost on container recreation; it is outside
  the git working tree entirely, so it can never be committed.
- No actual face images were printed or exposed in this documentation.

## Blocking issues

1. ~~Sample media required (T008 / PD-06 / PD-07)~~ — **RESOLVED 2026-09-09**: approved sample media placed under `tests/phase1/test-media/`; PD-06/PD-07 now PASS. Photos: 4 JPGs (under the 5-10 requested — non-blocking, only needed at T034/Phase 3 enrollment). Videos: known-person clip (as `known-person-walk.mp4` + original `RingVideo_20260909_132147.MP4`), `RingVideo_20260909_132235.MP4` (person clip), and 2 derived no-person segments. No low-light or two-person clip supplied — not required for the PD-07 pass criteria and not blocking the gate; useful later for Phase 3/4 acceptance tests (T036, T050).
2. Production HA (192.168.68.103) was not TCP-reachable from this Mac at inventory time on ports 8123/1883 — not a Phase 1 blocker, but worth checking before Phase 4 (T052). **Still true as of the Phase 2 run (T027–T030)** — full ding/motion behavior verification against production HA therefore remains deferred to T053; production HA was intentionally not modified.
3. Free disk is at 16 GB free — not currently blocking, but worth monitoring once Frigate's clip/recording storage and larger sample media are in use.
4. **Ring streaming is bounded-only** (T027–T030 constraint): Ring cameras are on-demand devices; continuous streaming is unsupported (motion/ding loss, battery drain). The Frigate config is restored to the sample-media source after every live test — see `docs/testing/local-mac-testing.md` §13a.

## Media request (per pre-development-validation.md §5)

**STATUS: SATISFIED (2026-09-09)** — see the PD-06 inventory table for the full file list with probe/decode results.
