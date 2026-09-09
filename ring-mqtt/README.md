# ring-mqtt (Ring video bridge) — Phase 2 (Constitution Phase 2)

**Status**: Configured in `docker-compose.yml` as the `ring-mqtt` service
(`tsightler/ring-mqtt:5.9.3`, pinned per constitution VI.3). **Bounded-use only.**

## What this is

`ring-mqtt` (tsightler/ring-mqtt) bridges Ring cloud devices to MQTT and exposes each Ring
camera as a local RTSP gateway (via the bundled go2rtc). Frigate can then ingest the live
Front Door stream — for short, deliberate test windows only (T028–T029).

## Critical constraint: no continuous streaming

Ring cameras are **cloud/on-demand devices**. `ring-mqtt` starts a live stream on demand
(when an RTSP client connects) and stops it ~5–10s after the last client disconnects.
Continuous/24x7 streaming is explicitly unsupported by the project: while a Ring camera is
actively streaming, it does **not** send motion/ding events, and sustained streaming drains
batteries and risks overheating. **Never leave the Ring stream running between test
windows** — restore the looped sample-media source in `frigate/config/config.yml` and stop
the RTSP client when done (see `docs/testing/local-mac-testing.md` §12/§15).

## Setup (one-time, interactive auth)

1. Create the data directory (gitignored — contains the Ring refresh token):

   ```bash
   mkdir -p ring-mqtt/data
   ```

2. **Authenticate** (interactive — requires your Ring account credentials and a 2FA/OTP
   code; do this yourself, never paste credentials into files or chat):

   ```bash
   docker run -it --rm \
     --mount type=bind,source="$(pwd)/ring-mqtt/data",target=/data \
     --entrypoint /app/ring-mqtt/init-ring-mqtt.js \
     tsightler/ring-mqtt:5.9.3
   ```

   This prompts for your Ring email/password and 2FA code, then writes:
   - `ring-mqtt/data/ring-state.json` — the **refresh token** (full account access;
     never commit, never share)
   - `ring-mqtt/data/config.json` — global config (created with defaults on first run)

3. **Point ring-mqtt at the Phase 1 isolated MQTT broker** by editing
   `ring-mqtt/data/config.json` (this file is gitignored):

   ```json
   { "mqtt_url": "mqtt://mosquitto:1883" }
   ```

   The `mosquitto` hostname resolves on the compose network. Keep any other options
   (`enable_cameras` defaults to `true`, which is what we need) as-is.

4. Start the service:

   ```bash
   docker compose up -d ring-mqtt
   ```

## Auth model & secrets

- ring-mqtt authenticates to **Ring cloud** with your Ring account via a **refresh token**
  stored in `ring-mqtt/data/ring-state.json` (created by the interactive CLI in step 2).
- The RTSP endpoint on this Mac is bound to `127.0.0.1:18554` **only** (loopback) and does
  **not** use `livestream_user`/`livestream_pass` for this Mac-local bounded test — see
  `docker-compose.yml`'s `ring-mqtt` service comment for why. **Production (Phase 5) must
  enable `livestream_user`/`livestream_pass`** per the ring-mqtt wiki (and constitution
  II.4) before exposing RTSP beyond the Mac.
- `ring-mqtt/data/` is gitignored. Verify with `git check-ignore -v ring-mqtt/data/` before
  any commit.

## RTSP form

```
Live:   rtsp://ring-mqtt:8554/<camera_id>_live     (inside compose network, e.g. from Frigate)
        rtsp://127.0.0.1:18554/<camera_id>_live    (from this Mac host)
Event:  rtsp://<host>:<port>/<camera_id>_event     (recorded playback; Ring Protect required)
```

The `<camera_id>` is discovered, **never invented** — see
`docs/testing/local-mac-testing.md` §12 for the discovery/probe steps.

## Notes

- Docker is ring-mqtt's "fully supported and highly preferred" install method (official
  image on Docker Hub). Version confirmed at pull time: **5.9.3** (image label
  `org.opencontainers.image.version`).
- Ring cloud is required for all streaming (Ring cameras have no local control API) — this
  project's recognition layer stays local (constitution I.3), but the Ring stream itself
  necessarily traverses Ring cloud.