# Contract: Frigate → MQTT → Home Assistant Event Interface

This is the interface Home Assistant's automations (the enrichment logic — research decision
#5) consume. It is a **semantic** contract: the fields our automations rely on, mapped onto
Frigate's general event/MQTT publishing pattern. Frigate's exact topic/payload field names
MUST be confirmed against the pinned Frigate version's own MQTT documentation during Phase 1
implementation (constitution VI.3 — pin and document significant dependencies); this contract
is what HA-side automations are written against, and should be updated if the pinned version's
wire format differs from what's assumed here.

## Topics consumed

| Topic pattern | Purpose |
|---|---|
| `frigate/events` | Person Detection Event lifecycle (`new` / `update` / `end`) and, when face recognition is enabled, the recognition outcome |
| `frigate/available` | Frigate's own availability (online/offline) — feeds constitution IV.2's "AI host offline" failure state |

## `frigate/events` payload (semantic shape)

```json
{
  "type": "new | update | end",
  "before": { "...": "previous event state, same shape as after" },
  "after": {
    "id": "string — Person Detection Event.event_id",
    "camera": "string — Camera Source.name, e.g. \"front_door\"",
    "label": "person",
    "sub_label": "<enrolled identity name string> | null",
    "sub_label_score": "<face-recognition confidence 0-1> | null/absent",
    "score": "<object/person-detection confidence 0-1> — NOT the recognition score",
    "top_score": "<best detection score seen for this object 0-1>",
    "start_time": "unix timestamp",
    "end_time": "unix timestamp | null (null while event is ongoing)",
    "false_positive": "boolean"
  }
}
```

> **Verified against Frigate 0.17.2 (T034-A, 2026-09-11) — corrects the earlier assumption.**
> On the wire, `after.sub_label` is a **scalar string** (the recognized identity name) or
> `null`; it is NOT a `[name, confidence]` array. The **face-recognition** confidence is a
> separate field, `sub_label_score` (populated only when an identity is recognized; may be
> absent/null otherwise — Frigate carries it via the event's `data.sub_label_score`,
> internally set from the `(name, score)` tuple in `events/maintainer.py`). `after.score`
> and `after.top_score` are the **object/person-detection** confidence and MUST NEVER be
> substituted for the recognition confidence.
```

## Mapping to the data model

| Our field | Source |
|---|---|
| Person Detection Event `event_id` | `after.id` |
| Person Detection Event `camera_source` | `after.camera` |
| Person Detection Event `processing_status` | `detected` while `end_time` is null or absent-but-arriving; `identity_unavailable` if `frigate/available` shows Frigate offline for this event's window |
| Recognition Result `status = Known` | `after.sub_label` is a non-null string AND matches an **active** entry in the Identity Library AND `after.sub_label_score` meets the confidence policy (research decision #9) AND the liveness check passes (FR-029) |
| Recognition Result `status = Unknown` | `after.sub_label` is null, OR present but `sub_label_score` is below the confidence policy, OR the liveness check fails |
| Recognition Result `confidence_score` | `after.sub_label_score` (face-recognition score) — **never** `after.score`/`after.top_score` (detection) |
| Recognition Result `matched_identity` | Known Identity whose `name` equals `after.sub_label`, only when `status = Known` |

## Validation rules carried from the spec

- A `Known` result MUST NOT be produced from `after.sub_label` alone without also checking
  it against an **active** (non-`removed`) Identity Library entry (FR-021).
- HA automations MUST treat a missing/stale `frigate/events` stream (per `frigate/available`
  or a stale `end_time`) as `Unavailable`, never silently as `Unknown` (FR-019, constitution
  IV.3).
- Two or more `after.camera`-matching events open within the notification dedup window are
  the multi-person case — HA automations MUST merge them into one Notification Event rather
  than firing one notification per event (FR-030).

## Topics published by our system

Home Assistant's own MQTT/notification pipeline (not a new topic we define) delivers the
final Notification Event via the existing `notify.mobile_app_*` service already verified in
the constitution (Article VIII.1) — no new outbound MQTT topic is introduced by this feature.
