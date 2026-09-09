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

With the config fixes above, the *only* remaining error in Frigate's logs for the `front_door` camera is `ffmpeg` failing to open `/media/test-source/known-person-walk.mp4` because that file does not exist yet — **T008 is still pending your sample media.** Frigate handles this gracefully (per-camera capture retry, not a container crash or restart loop), which is itself a good sign for constitution IV.2 ("every external dependency needs a failure state").

### Infrastructure ingestion proof (not a person-detection test)

To confirm the actual streaming mechanics work end-to-end independent of T008, a synthetic, non-biometric test-pattern clip (`ffmpeg`'s `testsrc`, no people, no photos, 5s color-bars) was generated locally and temporarily swapped into the go2rtc stream. Result: `camera_fps: 5.0`, `process_fps: 5.0`, zero errors, via Frigate's `/api/stats`. The config was reverted back to reference the real (pending) filename immediately after. **This proves the pipeline plumbing, not person detection** — PD-07's actual person-detection test remains blocked on real sample media (see below).

**Status: PASS**

## PD-06 — Media Validation

**Status: BLOCKED.** No approved sample media has been provided yet (T008). Per your explicit instruction, no biometric test media was fabricated or substituted. Nothing to probe/decode/normalize/report on until you provide the photos and videos requested below.

## PD-07 — Person Detection Validation

**Status: BLOCKED** (depends on PD-06 / T008). Cannot run the person-positive or person-negative test without real sample video.

## PD-08 — Home Assistant Integration Validation (mechanics-only scope)

- Throwaway Home Assistant container started (`ghcr.io/home-assistant/home-assistant:2024.12.5`), separate from the production instance at `192.168.68.103`: **PASS** — reachable at `http://localhost:8124/` (HTTP 302 to onboarding, expected for a fresh instance)
- Frigate and the throwaway HA share the same isolated MQTT broker: **PASS** (both point at the `mosquitto` service in `docker-compose.yml`)
- At least one Frigate-generated event/entity visible in the throwaway HA: **NOT YET RUN** — this requires the Frigate HA integration to be configured inside the throwaway instance, which in turn is most meaningfully exercised once real person-detection events exist (T008/T016). Deferred to resume immediately after T008/T016 unblock.
- "Existing Ring automations remain unaffected" check: **deliberately out of scope here** — a blank throwaway HA has no existing automations to protect; the real check happens later against production HA (research.md #11, tasks.md T053).

**Status: PARTIAL** (broker/instance mechanics proven; event-visibility check waiting on T008/T016)

## PD-09 — Face Recognition Hardware Gate

**Status: DEFERRED.** Per tasks.md, this is explicitly Phase 3's task (T031), not part of this Foundational gate. What's already known: this host is Intel x86_64 (`i9-9980HK`), which is the correct CPU family for Frigate's AVX/AVX2 requirement, confirmed via `/grill-me` earlier in this project. The specific AVX2 instruction-set check against the *pinned Frigate version's documented requirements* has **not** been performed and is intentionally left to T031, not assumed here.

`FACE_RECOGNITION_LOCAL = DEFERRED_PENDING_PHASE_3_VERIFICATION` (not yet `READY`, not asserted `UNSUPPORTED` — genuinely not yet checked against documented requirements, only the CPU family is known).

## PD-10 — No Development Before Green Baseline

**T019 gate result: FAIL (incomplete).** PD-01 through PD-05 and PD-08's mechanics pass; PD-06 and PD-07 are blocked on user-provided sample media (T008); PD-08's full scope and PD-09 have downstream dependencies not yet met. Per the constitution and your explicit instructions, implementation tasks (T020+) do not begin until this gate passes in full.

## Blocking issues

1. **Sample media required (T008 / PD-06 / PD-07)** — see the request below. This is the single blocker preventing T019 from fully passing.
2. Production HA (192.168.68.103) was not TCP-reachable from this Mac at inventory time on ports 8123/1883 — not a Phase 1 blocker, but worth checking before Phase 4 (T052).
3. Free disk is at 16 GB free — not currently blocking, but worth monitoring once Frigate's clip/recording storage and larger sample media are in use.

## Media request (per pre-development-validation.md §5)

**Photos** — 5-10 of one person you're authorized to enroll: 2-3 clear front-facing daylight, 1-2 indoor, 1-2 mild expression variation, 1 mild angle variation.

**Videos** — 3-5 clips, ~5-30s each:
1. known person walking toward the camera
2. unknown/untrained person walking toward the camera
3. ordinary motion, no person
4. low-light/evening person clip
5. optional: two people together

Place them under `tests/phase1/test-media/` (already gitignored — confirmed via `.gitignore`, never committed). Suggested filenames matching what's already referenced in `frigate/config/config.yml` and `.env.example`: `known-person-walk.mp4`, `unknown-person-walk.mp4`, `no-person-motion.mp4`, `low-light-person.mp4`, plus the enrollment photos in a subfolder of your choice.
