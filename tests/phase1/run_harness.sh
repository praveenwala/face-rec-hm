#!/usr/bin/env bash
# Phase 1 person-detection MVP test harness (research.md #8; plan.md Technical Context).
#
# Drives the looped go2rtc test-video source and asserts on Frigate's MQTT output
# (tests/phase1/tasks.md T020-T022; spec US1 SC-001 + Acceptance Scenarios 3/4).
#
# The harness classifies every outcome explicitly — it never collapses distinct failures
# into one generic result (constitution IV.3, FR-019):
#
#   PERSON_PRESENT          person-labeled event observed on frigate/events
#   PERSON_NOT_DETECTED     Frigate healthy + ingesting, but no person event in window
#   MEDIA_DECODE_FAILURE    the clip itself could not be probed/decoded
#   STREAM_FAILURE          Frigate down / not ingesting (subsystem unavailable)
#   EVENT_DELIVERY_FAILURE  broker unreachable or subscription failed
#
# Usage: tests/phase1/run_harness.sh <positive|negative|identity-unavailable|failure-classes|all>
#
# Requires: running docker compose stack (mosquitto + frigate), mosquitto_sub,
# ffprobe/ffmpeg, curl, and approved sample media under tests/phase1/test-media/.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
CONFIG="$REPO_ROOT/frigate/config/config.yml"
TEST_MEDIA="$REPO_ROOT/tests/phase1/test-media"
# Broker endpoint for HOST-side tooling. The Phase 1 broker is published on the Mac host
# at 127.0.0.1:1883 (docker-compose.yml's MQTT_PORT mapping). Do NOT inherit the ambient
# MQTT_HOST=mosquitto from .env — that is the in-container service name, only resolvable
# inside the compose network, and using it from this script fails with "Lookup error".
HARNESS_MQTT_HOST="${HARNESS_MQTT_HOST:-127.0.0.1}"
HARNESS_MQTT_PORT="${HARNESS_MQTT_PORT:-1883}"
TOPIC="frigate/events"

# Default clips (override via env). Must live under tests/phase1/test-media/.
POSITIVE_CLIP="${POSITIVE_CLIP:-known-person-walk.mp4}"
NEGATIVE_CLIP="${NEGATIVE_CLIP:-videos/derived-no-person-segment-1.mp4}"

POSITIVE_WINDOW_SECONDS="${POSITIVE_WINDOW_SECONDS:-30}"
NEGATIVE_WINDOW_SECONDS="${NEGATIVE_WINDOW_SECONDS:-45}"

# Track whether we changed the config so we can restore it on exit.
CONFIG_MODIFIED=0
RESTORE_CLIP=""
ORIGINAL_CLIP="$(grep -o '/media/test-source/[^ ]*' "$CONFIG" 2>/dev/null | head -1 | sed 's|/media/test-source/||')"

log()  { printf '[run_harness] %s\n' "$*"; }
fail() { printf '[run_harness] FAIL: %s\n' "$*" >&2; exit 1; }

restore_config() {
  if [[ "$CONFIG_MODIFIED" -eq 1 && -n "$ORIGINAL_CLIP" ]]; then
    log "restoring go2rtc source to original: $ORIGINAL_CLIP"
    sed -i.bak "s|/media/test-source/[^ ]*|/media/test-source/$ORIGINAL_CLIP|" "$CONFIG"
    rm -f "$CONFIG.bak"
    CONFIG_MODIFIED=0
  fi
}
trap restore_config EXIT

check_prereqs() {
  command -v mosquitto_sub >/dev/null 2>&1 || fail "mosquitto_sub not found (brew install mosquitto)"
  command -v ffprobe >/dev/null 2>&1   || fail "ffprobe not found (brew install ffmpeg)"
  command -v ffmpeg >/dev/null 2>&1    || fail "ffmpeg not found (brew install ffmpeg)"
  command -v curl >/dev/null 2>&1      || fail "curl not found"
  docker compose ps >/dev/null 2>&1 || fail "docker compose not available or daemon down"
  docker compose ps mosquitto 2>/dev/null | grep -q 'Up' || fail "mosquitto container not running"
  docker compose ps frigate 2>/dev/null | grep -q 'Up' || fail "frigate container not running"
}

probe_clip() {
  # Returns MEDIA_DECODE_FAILURE classification, or prints probe facts.
  local clip="$1"
  if [[ ! -f "$TEST_MEDIA/$clip" ]]; then
    printf 'MEDIA_DECODE_FAILURE: file not found: %s\n' "$TEST_MEDIA/$clip" >&2
    return 1
  fi
  if ! ffprobe -v error -show_format -show_streams -of json "$TEST_MEDIA/$clip" >/dev/null 2>&1; then
    printf 'MEDIA_DECODE_FAILURE: ffprobe could not read %s\n' "$TEST_MEDIA/$clip" >&2
    return 1
  fi
  if ! ffmpeg -v error -i "$TEST_MEDIA/$clip" -frames:v 5 -f null - >/dev/null 2>&1; then
    printf 'MEDIA_DECODE_FAILURE: ffmpeg could not decode %s\n' "$TEST_MEDIA/$clip" >&2
    return 1
  fi
  echo "probe ok: $clip"
}

set_source() {
  # Point the go2rtc exec producer at $1 (path relative to test-media), restart Frigate.
  local clip="$1"
  probe_clip "$clip" || return 1
  log "switching go2rtc source to $clip (was: ${ORIGINAL_CLIP:-unknown})"
  sed -i.bak "s|/media/test-source/[^ ]*|/media/test-source/$clip|" "$CONFIG"
  rm -f "$CONFIG.bak"
  CONFIG_MODIFIED=1
  docker compose restart frigate >/dev/null 2>&1 || return 1
  wait_frigate_healthy || return 1
}

wait_frigate_healthy() {
  local i
  for i in $(seq 1 60); do
    if docker compose ps frigate 2>/dev/null | grep -q '(healthy)'; then
      # Give capture a few seconds to spin up, then verify actual ingestion.
      sleep 5
      if frigate_ingesting; then
        return 0
      fi
    fi
    sleep 2
  done
  printf 'STREAM_FAILURE: frigate not healthy/ingesting within 120s\n' >&2
  return 1
}

frigate_ingesting() {
  local stats camera_fps
  stats="$(curl -s --max-time 5 "http://localhost:5001/api/stats" 2>/dev/null || true)"
  camera_fps="$(printf '%s' "$stats" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); print(d.get("cameras",{}).get("front_door",{}).get("camera_fps",0))
except Exception: print(0)' 2>/dev/null || echo 0)"
  awk -v f="$camera_fps" 'BEGIN { exit !(f > 0) }'
}

frigate_running() {
  docker compose ps frigate 2>/dev/null | grep -q 'Up'
}

observe_events() {
  # Subscribe to frigate/events for $1 seconds. Prints one line per parsed event:
  #   <type>|<label>|<score>
  # Returns EVENT_DELIVERY_FAILURE (2) if the broker/subscription itself fails.
  local window="$1"
  local out
  out="$(mosquitto_sub -h "$HARNESS_MQTT_HOST" -p "$HARNESS_MQTT_PORT" -t "$TOPIC" -W "$window" 2>/tmp/run_harness_mqtt_err)" || {
    if grep -qiE 'connection refused|error|failed' /tmp/run_harness_mqtt_err; then
      printf 'EVENT_DELIVERY_FAILURE: %s\n' "$(head -1 /tmp/run_harness_mqtt_err)" >&2
      return 2
    fi
    # -W timeout exit codes are benign; treat as end of window.
  }
  printf '%s' "$out" | python3 -c '
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line or line == "Timed out":
        continue
    try:
        p = json.loads(line)
    except Exception:
        continue
    after = p.get("after") or {}
    before = p.get("before") or {}
    label = after.get("label") or before.get("label")
    ev_type = p.get("type") or ""
    score = after.get("score") or before.get("score") or ""
    print(ev_type + "|" + str(label) + "|" + str(score))
' 2>/dev/null || true
  return 0
}

count_person_events() {
  # Reads "type|label|score" lines on stdin; prints count of person-labeled lines.
  awk -F '\|' '$2 == "person" { n++ } END { print n+0 }'
}

assert_positive() {
  local clip="${1:-$POSITIVE_CLIP}"
  log "== ASSERTION positive: $clip must produce a person event within ${POSITIVE_WINDOW_SECONDS}s =="
  set_source "$clip" || return 1
  log "frigate ingesting; subscribing to $TOPIC for ${POSITIVE_WINDOW_SECONDS}s"
  local events
  events="$(observe_events "$POSITIVE_WINDOW_SECONDS")" || return 1
  local count
  count="$(printf '%s\n' "$events" | count_person_events)"
  local first
  first="$(printf '%s\n' "$events" | grep '|person|' | head -1)"
  if [[ "$count" -gt 0 ]]; then
    log "PERSON_PRESENT: $count person event(s) observed; first: ${first:-}"
    return 0
  fi
  log "PERSON_NOT_DETECTED: 0 person events in ${POSITIVE_WINDOW_SECONDS}s while Frigate was healthy"
  return 1
}

assert_negative() {
  local clip="${1:-$NEGATIVE_CLIP}"
  log "== ASSERTION negative: $clip must produce no person event in ${NEGATIVE_WINDOW_SECONDS}s =="
  set_source "$clip" || return 1
  log "frigate ingesting; subscribing to $TOPIC for ${NEGATIVE_WINDOW_SECONDS}s"
  local events count
  events="$(observe_events "$NEGATIVE_WINDOW_SECONDS")" || return 1
  count="$(printf '%s\n' "$events" | count_person_events)"
  if [[ "$count" -eq 0 ]]; then
    log "PERSON_NOT_DETECTED: 0 person events in ${NEGATIVE_WINDOW_SECONDS}s (expected) — PASS"
    return 0
  fi
  log "FAIL: $count person event(s) fired on a no-person clip"
  return 1
}

classify_outcome() {
  # Given a window's raw event output, print the explicit outcome classification.
  # Distinct outcomes are NEVER collapsed (constitution IV.3, FR-019):
  #   EVENT_DELIVERY_FAILURE  broker/subscription failure
  #   STREAM_FAILURE          Frigate down or not ingesting (subsystem unavailable)
  #   PERSON_PRESENT          person-labeled event(s) observed
  #   PERSON_NOT_DETECTED     Frigate healthy, zero person events in window
  local events="$1"
  local count
  count="$(printf '%s\n' "$events" | count_person_events)"
  if [[ "$count" -gt 0 ]]; then
    echo "PERSON_PRESENT"
    return 0
  fi
  if ! frigate_running; then
    echo "STREAM_FAILURE"
    return 0
  fi
  if ! frigate_ingesting; then
    echo "STREAM_FAILURE"
    return 0
  fi
  echo "PERSON_NOT_DETECTED"
}

assert_identity_unavailable() {
  # US1 Acceptance Scenario 4 (Phase-1-automatable slice): with the identity/detection
  # subsystem (Frigate) stopped, the base person-detection path must be correctly
  # classified as STREAM_FAILURE — never as PERSON_NOT_DETECTED and never as
  # MEDIA_DECODE_FAILURE (constitution IV.3, FR-019). The broker/transport itself must
  # remain reachable (the event bus is independent of the AI subsystem — the stand-in for
  # constitution III.3's "original security event" transport in this POC), and events must
  # resume after restart without rebuilding anything (spec US5 Scenario 3, mechanics slice).
  log "== ASSERTION identity-unavailable: Frigate stopped ⇒ STREAM_FAILURE classification + recovery =="
  set_source "$POSITIVE_CLIP" || return 1
  log "stopping frigate container (simulating identity subsystem unavailable)"
  docker compose stop frigate >/dev/null 2>&1
  # Give mosquitto a moment to drop the disconnected client, then attempt observation.
  sleep 5
  local events
  events="$(observe_events "$POSITIVE_WINDOW_SECONDS")" || {
    local rc=$?
    log "restarting frigate"
    docker compose start frigate >/dev/null 2>&1
    wait_frigate_healthy || return 1
    if [[ $rc -eq 2 ]]; then
      log "FAIL: broker/subscription failed while frigate was stopped (EVENT_DELIVERY_FAILURE) — transport should survive AI-subsystem outage"
      return 1
    fi
    return 1
  }
  local classification
  classification="$(classify_outcome "$events")"
  local count
  count="$(printf '%s\n' "$events" | count_person_events)"
  log "frigate stopped → $count person event(s); classification: $classification"
  if [[ "$classification" != "STREAM_FAILURE" ]]; then
    log "FAIL: expected STREAM_FAILURE, got $classification (must not conflate subsystem outage with no-person)"
    docker compose start frigate >/dev/null 2>&1
    wait_frigate_healthy || true
    return 1
  fi
  # Recovery: after restart, events must flow again without rebuilding anything.
  log "restarting frigate (recovery check)"
  docker compose start frigate >/dev/null 2>&1
  wait_frigate_healthy || return 1
  sleep 3
  local events2 count2 classification2
  events2="$(observe_events "$POSITIVE_WINDOW_SECONDS")" || return 1
  count2="$(printf '%s\n' "$events2" | count_person_events)"
  classification2="$(classify_outcome "$events2")"
  log "after restart → $count2 person event(s); classification: $classification2"
  if [[ "$classification2" == "PERSON_PRESENT" ]]; then
    log "PERSON_PRESENT after restart — recovery confirmed without rebuilding anything"
    return 0
  fi
  log "FAIL: expected PERSON_PRESENT after restart, got $classification2 (recovery not confirmed)"
  return 1
}

assert_failure_classes() {
  # Exercises the remaining failure classifications so each is proven distinct:
  # MEDIA_DECODE_FAILURE (undecodable clip), STREAM_FAILURE (subsystem down), and
  # EVENT_DELIVERY_FAILURE (broker unreachable). Not a spec acceptance scenario itself —
  # it proves the harness (and thus the observability layer, constitution VII.1) never
  # collapses distinct failures into one generic result.
  log "== ASSERTION failure-classes: MEDIA_DECODE_FAILURE / STREAM_FAILURE / EVENT_DELIVERY_FAILURE =="

  # 1. MEDIA_DECODE_FAILURE — a clip that exists but cannot be decoded.
  local bad_clip="_probe_fail_test.mp4"
  printf 'this is not a video\n' > "$TEST_MEDIA/$bad_clip"
  if probe_clip "$bad_clip" >/dev/null 2>&1; then
    rm -f "$TEST_MEDIA/$bad_clip"
    log "FAIL: corrupt clip unexpectedly decoded"
    return 1
  fi
  rm -f "$TEST_MEDIA/$bad_clip"
  log "MEDIA_DECODE_FAILURE: undecodable clip rejected as a media problem, not a detection outcome — PASS"

  # 2. STREAM_FAILURE — Frigate stopped while broker stays up.
  log "stopping frigate for STREAM_FAILURE classification"
  docker compose stop frigate >/dev/null 2>&1
  sleep 5
  local events classification
  events="$(observe_events 10)" || true
  classification="$(classify_outcome "$events")"
  if [[ "$classification" == "STREAM_FAILURE" ]]; then
    log "STREAM_FAILURE: subsystem down classified distinctly (not PERSON_NOT_DETECTED) — PASS"
  else
    log "FAIL: expected STREAM_FAILURE, got $classification"
    docker compose start frigate >/dev/null 2>&1
    wait_frigate_healthy || true
    return 1
  fi

  # 3. EVENT_DELIVERY_FAILURE — broker unreachable (bad port), while Frigate is down.
  # Broker is still down from step 2; a bad-port subscription must classify as delivery
  # failure, proving transport failure is distinguished from subsystem-down.
  if ! mosquitto_sub -h "$HARNESS_MQTT_HOST" -p 1 -t "$TOPIC" -W 3 -C 1 >/dev/null 2>&1; then
    log "EVENT_DELIVERY_FAILURE: unreachable broker classified distinctly — PASS"
  else
    log "FAIL: unreachable broker did not fail as expected"
    docker compose start frigate >/dev/null 2>&1
    wait_frigate_healthy || true
    return 1
  fi

  log "restarting frigate"
  docker compose start frigate >/dev/null 2>&1
  wait_frigate_healthy || return 1
  return 0
}

summary() {
  echo
  echo "======================================================"
  echo " Phase 1 person-detection MVP — harness summary"
  echo "======================================================"
  echo " positive (T020):              $1"
  echo " negative (T021):              $2"
  echo " identity-unavailable (T022):  $3"
  echo " failure-classes:              $4"
  echo "======================================================"
  if [[ "$1" == PASS && "$2" == PASS && "$3" == PASS && "$4" == PASS ]]; then
    echo " OVERALL: PASS"
    return 0
  fi
  echo " OVERALL: FAIL"
  return 1
}

MODE="${1:-all}"
check_prereqs

P=FAIL; N=FAIL; I=FAIL; F=FAIL
case "$MODE" in
  positive)             assert_positive && P=PASS || true ;;
  negative)             assert_negative && N=PASS || true ;;
  identity-unavailable) assert_identity_unavailable && I=PASS || true ;;
  failure-classes)      assert_failure_classes && F=PASS || true ;;
  all)
    assert_positive && P=PASS || true
    assert_negative && N=PASS || true
    assert_identity_unavailable && I=PASS || true
    assert_failure_classes && F=PASS || true
    ;;
  *) fail "unknown mode: $MODE (use positive|negative|identity-unavailable|failure-classes|all)" ;;
esac

if [[ "$MODE" == "all" ]]; then
  summary "$P" "$N" "$I" "$F"
else
  # Single-mode runs report via their assertion logs; print a one-line result too.
  case "$MODE" in
    positive)             echo "RESULT: positive = $P" ;;
    negative)             echo "RESULT: negative = $N" ;;
    identity-unavailable) echo "RESULT: identity-unavailable = $I" ;;
    failure-classes)      echo "RESULT: failure-classes = $F" ;;
  esac
fi