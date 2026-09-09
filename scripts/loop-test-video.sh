#!/usr/bin/env bash
# Phase 1 test-video helper (research.md #3; pre-development-validation.md PD-06).
#
# The actual RTSP looping that Frigate ingests happens inside its own bundled go2rtc
# ("exec" producer in frigate/config/config.yml) — that's the real Phase 1 transport.
# This script is the pre-flight/dev-convenience half: it validates a candidate test clip
# BEFORE you point frigate/config/config.yml at it, so a bad file fails fast and visibly
# (MEDIA_DECODE_FAILURE) instead of silently breaking Frigate's go2rtc stream.
#
# Usage: scripts/loop-test-video.sh <path-to-video> [--play]

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <path-to-video> [--play]" >&2
  exit 2
fi

VIDEO_PATH="$1"
PLAY="${2:-}"

if [[ ! -f "$VIDEO_PATH" ]]; then
  echo "MEDIA_DECODE_FAILURE: file not found: $VIDEO_PATH" >&2
  exit 1
fi

if ! command -v ffprobe >/dev/null 2>&1; then
  echo "ERROR: ffprobe not found on PATH. Install ffmpeg (brew install ffmpeg)." >&2
  exit 1
fi

echo "Probing: $VIDEO_PATH"
if ! PROBE_JSON=$(ffprobe -v error -show_format -show_streams -of json "$VIDEO_PATH" 2>/tmp/ffprobe_err.log); then
  echo "MEDIA_DECODE_FAILURE: ffprobe could not read $VIDEO_PATH" >&2
  cat /tmp/ffprobe_err.log >&2
  exit 1
fi

echo "$PROBE_JSON" | python3 -c '
import json, sys
data = json.load(sys.stdin)
fmt = data.get("format", {})
video_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
print("  container:", fmt.get("format_name"))
print("  duration: ", fmt.get("duration", "unknown"), "s")
if video_streams:
    v = video_streams[0]
    print("  codec:    ", v.get("codec_name"))
    print("  size:     ", v.get("width"), "x", v.get("height"))
    print("  fps:      ", v.get("r_frame_rate"))
else:
    print("  WARNING: no video stream detected")
'

# Confirm ffmpeg can actually decode a few frames end-to-end, not just parse metadata.
if ! ffmpeg -v error -i "$VIDEO_PATH" -frames:v 5 -f null - 2>/tmp/ffmpeg_decode_err.log; then
  echo "MEDIA_DECODE_FAILURE: ffmpeg could not decode $VIDEO_PATH" >&2
  cat /tmp/ffmpeg_decode_err.log >&2
  exit 1
fi

echo "Decode OK: $VIDEO_PATH"

if [[ "$PLAY" == "--play" ]]; then
  if command -v ffplay >/dev/null 2>&1; then
    ffplay -autoexit "$VIDEO_PATH"
  else
    echo "ffplay not found; skipping playback preview." >&2
  fi
fi

echo
echo "To use this clip as the Phase 1 Frigate source, copy/symlink it into"
echo "tests/phase1/test-media/known-person-walk.mp4 (or update the filename in"
echo "frigate/config/config.yml's go2rtc exec producer to match)."
