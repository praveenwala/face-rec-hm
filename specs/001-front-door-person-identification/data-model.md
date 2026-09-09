# Phase 1 Data Model: Front Door Person Identification

Derived from the spec's Key Entities section, sharpened with the functional requirements and
clarifications resolved in `/speckit-clarify` and the two `/grill-me` sessions. This is a
conceptual model — it maps onto Frigate's own event/MQTT schema plus a small amount of
Home-Assistant-side state, not a new database (constitution: no database is introduced;
Storage is local filesystem only).

## Entities

### Person Detection Event
The base security event; exists independently of any identity outcome (FR-002, FR-017).

| Field | Type | Notes |
|---|---|---|
| `event_id` | string | Frigate event id |
| `timestamp` | datetime | When the person was detected |
| `camera_source` | → Camera Source | Which camera produced this event |
| `processing_status` | enum: `detected`, `identity_attempted`, `identity_unavailable` | `identity_unavailable` covers FR-019's "unavailable/stale" case, distinct from a genuine Unknown result |
| `evidence_reference` | string, optional | Snapshot/clip reference, when available (FR-026) |

**Relationships**: one Person Detection Event → zero-or-one Recognition Result (zero when
identity processing was unavailable); many Person Detection Events → one Camera Source.

**Validation rules**: MUST be created even when identity recognition cannot produce a known
match (FR-002); MUST NOT be suppressed by identity-recognition failure (FR-017).

### Known Identity
A person intentionally enrolled by the homeowner (constitution II.1 — explicit enrollment
only).

| Field | Type | Notes |
|---|---|---|
| `identity_id` | string | Stable internal id |
| `name` | string, **unique** | FR-031 — enforced unique per enrolled person; enrollment of a duplicate name MUST be rejected or require disambiguation |
| `reference_data` | reference, stored outside the repo | Approved face reference images/embeddings (research decision #6) |
| `relationship_category` | → Relationship Category, optional | May be absent (US3 acceptance scenario 2 — system reports identity without inventing a category) |
| `enrollment_status` | enum: `active`, `removed` | FR-020/FR-021 |
| `created_at` / `updated_at` | datetime | `updated_at` changes when reference data is refined (FR-027) |

**Relationships**: one Known Identity → zero-or-one Relationship Category.

**Validation rules**: created only via explicit enrollment (FR-003); a `removed` identity
MUST NOT be reported as that identity in any subsequent recognition (FR-021); a new face MUST
NOT silently create an identity (FR-022, constitution II.1).

### Recognition Result
The outcome of identity processing for one Person Detection Event.

| Field | Type | Notes |
|---|---|---|
| `result_id` | string | |
| `person_detection_event_id` | → Person Detection Event | |
| `status` | enum: `Known`, `Unknown`, `Unavailable`, `Failed` | The 4 states SC-012 requires the homeowner be able to distinguish |
| `matched_identity` | → Known Identity, optional | Present only when `status = Known` |
| `confidence_score` | number | Frigate's native face-recognition score (research decision #9) |
| `liveness_check` | enum: `pass`, `fail`, `not_applicable` | FR-029 — a non-live representation (photo/screen/reflection) MUST NOT be sufficient for `Known` |
| `timestamp` | datetime | |

**State transitions** (III.1 — person detection always comes first):

```text
Person Detection Event created
  → identity processing available?
      no  → Recognition Result: status = Unavailable
      yes → usable face present?
              no  → Recognition Result: status = Unknown
              yes → liveness check passes AND confidence meets policy AND matches an
                    enrolled identity?
                      no  → Recognition Result: status = Unknown
                      yes → Recognition Result: status = Known, matched_identity = <id>
  (unhandled processing error at any step) → Recognition Result: status = Failed
```

**Validation rules**: `Unknown` MUST be preferred over a low-confidence or ambiguous match
(FR-006); `Unavailable`/`Failed`/stale data MUST remain distinct from a genuine `Unknown`
result (FR-019, constitution IV.3); a non-live face representation MUST resolve to `Unknown`,
never `Known` (FR-029).

### Relationship Category
A small, fixed initial enum (FR-009) — not a freeform value.

| Value |
|---|
| Family |
| Friend |
| Neighbor |
| Other Known |

**Validation rules**: never inferred from appearance (FR-007, constitution III.2); assigned
explicitly and is editable (constitution III.2).

### Notification Event
The user-facing alert produced from one or more Person Detection Events.

| Field | Type | Notes |
|---|---|---|
| `notification_id` | string | |
| `source_events` | list of → Person Detection Event | **Plural** — FR-030: a single notification lists every person identified in one Front Door event, not one notification per person |
| `content` | list of `{ display: name+relationship \| "Unknown" }` | One entry per identified person in the source events |
| `dedup_key` | string | `(identified_person, 5-minute rolling window)` — FR-016's default policy |
| `created_at` / `delivered_at` | datetime | Delivery target: within 15s of the enriched event reaching HA (SC-005/SC-006) |

**Validation rules**: at most one notification per identified person (or per Unknown) within
the rolling 5-minute window (FR-016); an unknown-person notification MUST clearly state
"unknown" (FR-015); multi-person events MUST merge into one notification (FR-030).

### Camera Source
The monitored entrance camera associated with an event.

| Field | Type | Notes |
|---|---|---|
| `source_id` | string | |
| `name` | string | Initial required value: `Front Door` (FR-023) |
| `stream_type` | enum: `test_video` (Phase 1), `rtsp_live` (Phase 2+) | |

**Validation rules**: the design MUST permit adding another camera source later without
changing the meaning of Known Identity, Recognition Result, or Relationship Category
(FR-024, SC-010) — none of those entities reference Camera Source directly except through
Person Detection Event, so this holds structurally.

### Identity Library
The aggregate of all Known Identities plus the relationship mapping. Not a separate
persisted entity beyond its members — represented physically as: (1) Frigate's face-library
data volume (outside the repo) for `reference_data`, and (2) the gitignored
`home-assistant/helpers/relationship_mapping.yaml` for the name→category mapping (research
decision #6).

**Validation rules**: under household control, not publicly exposed by default (FR-028,
constitution II.4).

## Entity Relationship Summary

```text
Camera Source (1) ──< (many) Person Detection Event (1) ──< (0..1) Recognition Result
                                                                        │
                                                                        │ (0..1, when Known)
                                                                        ▼
                                                                  Known Identity (1) ──(0..1)──> Relationship Category
                                                                        ▲
                                                                        │ member of
                                                                  Identity Library

Person Detection Event (many) ──< (grouped into) Notification Event
```
