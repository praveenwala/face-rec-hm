# MQTT-B5 — Production Receive-Side Verification (2026-09-17)

**Feature**: [Front Door Person Identification](../../specs/001-front-door-person-identification/spec.md)
**Status**: VERIFICATION / DOCUMENTATION ONLY. Fresh operator-executed, read-only verification on
the production Raspberry Pi (HA Terminal & SSH add-on), performed 2026-09-17. **No production
config was changed to produce this evidence** — see §5.
**Supersedes (for CURRENT state only):** the "not yet verified" / "BLOCKED" MQTT-receive-side and
automation-deployment conclusions in [gate-a-results.md](gate-a-results.md) §MQTT and
[mqtt-state-reconciliation.md](mqtt-state-reconciliation.md) §4, and the "not deployed" /
"missing" assumptions in [live-ha-integration-preflight.md](live-ha-integration-preflight.md).
Those documents remain historically accurate as of their own capture dates; they are not rewritten
— this record is the current truth as of 2026-09-17.

---

## 1. What changed since the last snapshot

`mqtt-state-reconciliation.md` (2026-09-14) established the broker + HA MQTT integration were
operational but left Blocker 1 (Frigate transport) open and recorded no HA automation changes.
Between that date and this verification, the following were separately built and committed
(see `git log -- home-assistant/`, already reflected in CLAUDE.md): the C2.1–C2.4 isolated
identity-normalization implementation/validation, the `frigate_person_end_normalization.yaml`
automation fragment, and the `frigate_event_integration_helpers.yaml` helper — plus the
(previously uncommitted, still uncommitted) MQTT-B5 dev-Frigate-to-production-broker wiring in
`docker-compose.yml`/`frigate/config/config.yml`. This document is the first fresh, operator-side
confirmation that those pieces are now live on production HA.

## 2. Fresh verified facts (operator-executed on the Pi, 2026-09-17)

| # | Fact | Result |
|---|---|---|
| 1 | HA MQTT integration UI status | Online |
| 2 | HA MQTT listener receives retained `frigate/available` | `online` |
| 3 | HA MQTT listener receives live `frigate/events` from `front_door` | YES |
| 4 | "Frigate person end normalization" automation | **DEPLOYED and ENABLED** |
| 5 | That automation actively triggers from `frigate/events` | YES |
| 6 | Non-`end` / non-`person` messages | correctly filtered (no spurious triggers) |
| 7 | A qualifying person/end event completed normalization and fired `frigate_person_normalized` | `outcome=IDENTITY_UNKNOWN`, `known=false`, `raw_identity=null`, `recognition_confidence=null`, `detection_confidence` populated |
| 8 | `input_text.frigate_last_processed_event_id` | exists, actively updating with real Frigate event IDs (dedup working) |
| 9 | `/homeassistant/helpers/relationship_mapping.generated.yaml` | **EXISTS on production** |
| 10 | `ha core check` | completed successfully |
| 11 | Front Door Doorbell Notification automation | enabled |
| 12 | Front Door Motion Notification automation | enabled |
| 13 | Normalization automation body | contains **no** `notify.*` action |
| 14 | Any HA/Frigate/MQTT/Ring config changed to obtain the above | **NO** |

`MUTATING_ACTIONS_PERFORMED = NO` · `LIVE_HA_UNCHANGED_BY_THIS_VERIFICATION = YES` (consistent
with the Gate A no-change discipline).

## 3. Interpretation

- **Transport (MQTT-B5)**: dev/POC Frigate → production Mosquitto broker is CONNECTED and
  actively delivering `frigate/events` traffic that production HA receives and acts on (item 3).
  This is real, current, and observed from **both** sides now (broker-side, 2026-09-17 earlier
  session; HA-side, this verification).
- **Normalization automation**: deployed, enabled, and correctly firing on real traffic — but the
  one observed qualifying event normalized to `IDENTITY_UNKNOWN`, not `IDENTITY_KNOWN`. This is
  expected and correct: the **Known path is still gated behind spec-001 T035** (sustained
  per-track recognition has not yet produced a stable `sub_label`/`sub_label_score` in any
  environment — dev or production; see CLAUDE.md/tasks.md). `IDENTITY_UNKNOWN` for a real,
  unenrolled/not-yet-recognized front-door event is the fail-closed behavior the C2 contract
  guarantees, not a defect.
- **Notification path**: still **not active**. The deployed automation only normalizes identity
  and fires an internal `frigate_person_normalized` HA event (item 13); no automation anywhere in
  this repo calls `notify.*` for the AI/Frigate path. Gate I ("Enable enriched notifications" in
  `live-ha-integration-preflight.md`) remains not executed.
- **Source of the traffic**: MQTT-B5's Frigate instance is still the **dev/POC stack on the Mac**,
  running the looped sample-media test video (per `docker-compose.yml`), not a live Ring camera
  feed. **The production household broker and the now-live normalization automation are
  currently processing simulated/test person detections, continuously, for as long as the dev
  Mac's Frigate container stays up and MQTT-B5 stays wired.** This is low-risk (no notification
  fires, no identity is stored, `Unknown` is the fail-closed default) but is a real, continuous
  cross-environment dependency worth being deliberate about — it ties production HA's event
  stream to a development machine's uptime and test-video loop, not any real-world signal.
- **Ring independence**: freshly reconfirmed, not just historical — both Ring automations
  (doorbell, motion) are enabled and, by construction, the normalization automation's trigger/
  condition/action body never references them (item 13 confirms no cross-wiring via `notify.*`
  either). `RING_SECURITY_PATH_DEPENDENT_ON_AI = NO` continues to hold, now freshly verified
  (2026-09-17) rather than only as of Gate A.

## 4. Explicit non-claims (do not over-read this verification)

- **T035 is NOT passed by this event.** One real `IDENTITY_UNKNOWN` normalization is expected
  fail-closed behavior, not evidence of (or against) the Known-path recognition-consistency work
  T035 is scoped to. T035 remains pending/deferred exactly as recorded in `tasks.md`.
- **No AI-driven notification has ever fired in production.** Only the internal
  `frigate_person_normalized` HA event has been observed.
- **The relationship mapping's contents were not read or exposed here** — only its *existence* at
  the documented path was confirmed by the operator. No identity/relationship/UUID data appears
  in this document or elsewhere in this repo.
- **This is not a claim that MQTT-B5 should stay wired long-term** — it is a point-in-time
  confirmation that it currently *is* wired and working, sourced from test media, decision left to
  the project owner.

## 5. No-change verification (this document)

- production files modified: NO
- automations/helpers modified or created: NO
- relationship mapping generated/deployed: NO (already present; not touched)
- HA reload/restart: NO
- Mosquitto/Frigate restart: NO
- MQTT publish (by this verification): NO — read-only `mosquitto_sub`/UI observation only
- identities/references modified: NO
- Ring config modified: NO
