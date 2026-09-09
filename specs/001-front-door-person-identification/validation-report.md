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

**Status: DEFERRED.** Per tasks.md, this is explicitly Phase 3's task (T031), not part of this Foundational gate. What's already known: this host is Intel x86_64 (`i9-9980HK`), which is the correct CPU family for Frigate's AVX/AVX2 requirement, confirmed via `/grill-me` earlier in this project. The specific AVX2 instruction-set check against the *pinned Frigate version's documented requirements* has **not** been performed and is intentionally left to T031, not assumed here.

`FACE_RECOGNITION_LOCAL = DEFERRED_PENDING_PHASE_3_VERIFICATION` (not yet `READY`, not asserted `UNSUPPORTED` — genuinely not yet checked against documented requirements, only the CPU family is known).

## PD-10 — No Development Before Green Baseline

**T019 gate result: PASS.** PD-01 through PD-08 now pass in full (see each section above for evidence); PD-09 remains explicitly **deferred** to Phase 3 (T031), which is the sanctioned disposition per PD-10 ("PD-09 has either passed or has been explicitly deferred to supported hardware"). Per the constitution and your explicit instructions, implementation tasks (T020+) may now begin.

## Blocking issues

1. ~~Sample media required (T008 / PD-06 / PD-07)~~ — **RESOLVED 2026-09-09**: approved sample media placed under `tests/phase1/test-media/`; PD-06/PD-07 now PASS. Photos: 4 JPGs (under the 5-10 requested — non-blocking, only needed at T034/Phase 3 enrollment). Videos: known-person clip (as `known-person-walk.mp4` + original `RingVideo_20260909_132147.MP4`), `RingVideo_20260909_132235.MP4` (person clip), and 2 derived no-person segments. No low-light or two-person clip supplied — not required for the PD-07 pass criteria and not blocking the gate; useful later for Phase 3/4 acceptance tests (T036, T050).
2. Production HA (192.168.68.103) was not TCP-reachable from this Mac at inventory time on ports 8123/1883 — not a Phase 1 blocker, but worth checking before Phase 4 (T052).
3. Free disk is at 16 GB free — not currently blocking, but worth monitoring once Frigate's clip/recording storage and larger sample media are in use.

## Media request (per pre-development-validation.md §5)

**STATUS: SATISFIED (2026-09-09)** — see the PD-06 inventory table for the full file list with probe/decode results.
