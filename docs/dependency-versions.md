# Pinned Dependency Versions (T057 / Constitution VI.3)

Authoritative record of the pinned versions the project runs. Every version below is taken
directly from the repository's committed configuration and/or verified against the running
containers — none are guessed. Update this file whenever a pinned version changes (constitution
VI.3: dependencies are pinned and their versions documented).

Recorded: 2026-09-15. Source of truth for each pin is cited in the "Pinned in" column.

## Core pipeline (Feature 001 — `docker-compose.yml`)

| Component | Pinned version | Pinned in | Verification |
|---|---|---|---|
| Frigate | `ghcr.io/blakeblackshear/frigate:0.17.2` | `docker-compose.yml` | Runtime `GET /api/version` → `0.17.2-3d4dd3a`; Frigate config `version: 0.17-0` (`frigate/config/config.yml`) |
| Mosquitto (MQTT broker) | `eclipse-mosquitto:2.0.18` | `docker-compose.yml` | Image tag pinned |
| go2rtc | `1.9.10` (revision `df95ce3`) | Bundled inside the Frigate `0.17.2` image (not separately pinned) | Runtime `go2rtc -version` → `go2rtc version 1.9.10 (df95ce3) linux/amd64`; go2rtc API `version: 1.9.10` |
| Home Assistant (throwaway dev instance) | `ghcr.io/home-assistant/home-assistant:2024.12.5` | `docker-compose.yml` | Image tag pinned. NOTE: this is the local throwaway HA; the production control plane is a separate Raspberry Pi 3 (see `docs/production/`), not this image. |
| ring-mqtt (Ring bridge) | `tsightler/ring-mqtt:5.9.3` | `docker-compose.yml` | Image tag pinned |

## Enrollment manager (Feature 002 — `docker-compose.enrollment.yml` / Dockerfiles)

Supplementary; not part of the constitution VI.3 core-pipeline list but pinned and recorded
for completeness.

| Component | Pinned version | Pinned in |
|---|---|---|
| Backend base image | `python:3.13-slim` | `enrollment-app/Dockerfile.backend` |
| Frontend build image | `node:22-alpine` | `enrollment-app/Dockerfile.frontend` |
| Frontend serve image | `nginx:1.27-alpine` | `enrollment-app/Dockerfile.frontend` |

## Notes

- **go2rtc is not independently pinned**: it ships inside the Frigate image, so its version is
  determined by the Frigate pin (`0.17.2` → go2rtc `1.9.10`). Changing the Frigate pin may change
  the bundled go2rtc version; re-verify with `docker exec <frigate> go2rtc -version` after any
  Frigate upgrade.
- **Frigate config schema version** (`version: 0.17-0` in `frigate/config/config.yml`) is the
  config-format version Frigate auto-migrated to on the `0.15.1 → 0.17.2` upgrade; it is distinct
  from the image tag.
- The production deployment doc (`docs/production/production-deployment.md`) also references these
  versions; this file is the consolidated, single-source pin record.
