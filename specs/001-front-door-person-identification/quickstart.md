# Quickstart: Validating Phase 1 (Mac POC)

This validates the Phase 1 slice of this feature end-to-end: Docker → isolated MQTT → Frigate
→ person detection → a throwaway Home Assistant instance sees the event. It does **not**
cover identity recognition, relationship mapping, or real notifications — those are Phase 3/4
and follow once their prerequisites are met (see `plan.md`'s phase-gating).

## Prerequisites

Complete `pre-development-validation.md` PD-01 through PD-08 first (PD-09's face-recognition
hardware gate does not block Phase 1, since Phase 1 doesn't enable face recognition). Confirm:

- Docker Desktop + Compose working (`docker version`, `docker compose version`)
- `mosquitto_pub`/`mosquitto_sub` available
- `ffprobe`/`ffplay` or VLC available
- Sample test video(s) present under `tests/phase1/test-media/` (see
  `pre-development-validation.md` §5 for what to provide)

## Setup

```bash
# From repo root
docker compose up -d mosquitto frigate ha-throwaway
```

Expected: all three containers report healthy (`docker compose ps`); Frigate's UI is
reachable locally; the throwaway HA instance's UI is reachable locally and separate from the
production Pi-hosted instance.

## Start the looped test video source

```bash
scripts/loop-test-video.sh tests/phase1/test-media/known-person-walk.mp4
```

Expected: go2rtc exposes an RTSP endpoint that Frigate's `frigate/config/config.yml` is
already pointed at; `ffplay`/VLC against that RTSP URL shows the looping clip.

## Run the automated harness

```bash
tests/phase1/run_harness.sh
```

Expected outcomes (maps to spec SC-001, SC-002, SC-004 in their Phase-1-automatable form):

- Feeding the "known/unknown person walking" clip produces a `frigate/events` message with
  `label: person` within a few seconds of the person entering frame.
- Feeding the "no person, ordinary motion" clip produces **no** person event.
- The harness prints a pass/fail summary; a failure MUST report which assertion failed, not
  just "test failed" (constitution VII — every stage must be debuggable).

## Confirm HA visibility (PD-08, mechanics only)

```bash
mosquitto_sub -h localhost -t 'frigate/events' -C 1
```

Then, in the throwaway HA instance's UI, confirm at least one Frigate-generated
event/entity is visible (constitution VII.1's "did Home Assistant receive it?" check, for the
mechanics-only scope decided in `/grill-me` — see `research.md` item 11 for why the
production-HA failure-isolation test is *not* part of this quickstart).

## Record the result

Fill in `validation-report.md` (PD-10) with the outcome of each step above before starting any
Phase 1 implementation task.

## Tear down

```bash
docker compose down
```

The throwaway HA instance and its data are disposable — no state from it should ever be
treated as a source of truth or migrated toward production.
