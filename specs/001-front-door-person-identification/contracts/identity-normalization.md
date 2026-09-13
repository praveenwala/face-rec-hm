# Contract: Identity Normalization (Feature 001, T034-C2.1)

Reference semantics for turning a parsed Frigate event (T034-A `FrigateEventParse`) plus a
loaded relationship mapping (T034-B/C1) into a normalized identity result. This document
describes the **reference model** (`bridge/identity_normalizer.py`, a pure test-only
library). The HA-side Jinja implementation (T034-C2.2+) MUST match these semantics; it is
**not** implemented yet. Synthetic identities only (`Known_Person_A`, etc.).

## Inputs

- `parsed_event`: T034-A `FrigateEventParse` (raw parsing stays in T034-A).
- `relationship_mapping`: the already-loaded mapping object `{schema_version, identities}`
  (the caller loads it; the normalizer never reads files).
- `mapping_status`: explicit availability signal — `LOADED | MISSING | MALFORMED | UNSUPPORTED`.

## Outcomes

`IDENTITY_KNOWN`, `IDENTITY_UNKNOWN`, `IDENTITY_DISABLED`, `IDENTITY_UNMAPPED`,
`MAPPING_UNAVAILABLE`, `RECOGNITION_FAILURE`, `IGNORED_NON_PERSON`.
(No `FACE_NOT_AVAILABLE` — the event data does not distinguish it from `IDENTITY_UNKNOWN`.)

## Deterministic precedence

1. Parser `IGNORED_NON_PERSON` (label != person) → `IGNORED_NON_PERSON`.
2. Parser `PARSE_ERROR`, or a person event whose `sub_label` was malformed (list/dict/number)
   → `RECOGNITION_FAILURE`.
3. Person event with no asserted identity (`sub_label` null/empty/whitespace) → `IDENTITY_UNKNOWN`.
4. Asserted identity but **missing/invalid recognition score** → `RECOGNITION_FAILURE`
   (fail-closed; see confidence rules).
5. Mapping globally unavailable/invalid → `MAPPING_UNAVAILABLE`
   (status != LOADED, mapping not an object, `schema_version` != integer 1, `identities` not an object).
6. Identity **absent** from a valid mapping → `IDENTITY_UNMAPPED`.
7. Matching entry **broken** (not an object, or `enabled` not a boolean, or — when
   `enabled=true` — invalid `relationship`/`person_uuid`/`display_name`) → `MAPPING_UNAVAILABLE`.
8. Matching entry with `enabled` exactly `false` → `IDENTITY_DISABLED`
   (established from `entry is object` + `enabled is bool false` **before** validating other
   fields; public trusted metadata stays null).
9. Otherwise fully valid → `IDENTITY_KNOWN`.

**Absent vs broken is deliberately distinguished:** an identity missing from the mapping is
`IDENTITY_UNMAPPED`; a present-but-corrupt entry is `MAPPING_UNAVAILABLE`.

## `known` rule

`known=true` **only** for `IDENTITY_KNOWN`, which requires ALL: person event; non-empty
scalar `sub_label`; valid numeric `sub_label_score`; mapping LOADED + `schema_version==1` +
`identities` object; matching entry object; `enabled` exactly boolean `true`; `relationship`
∈ {Family, Friend, Neighbor, Other Known}; non-empty `person_uuid`; non-empty `display_name`.
Everything else is `known=false`. Relationship is never inferred.

## Disabled semantics

A mapping entry with `enabled=false` explicitly disables that Frigate identity. It resolves
to `IDENTITY_DISABLED`, `known=false`, with `identity`/`person_uuid`/`relationship` **null**
in the public result (disabled metadata is diagnostics-only, never trusted). This holds even
if the entry's other fields are malformed — the explicit disable is authoritative.

## Confidence semantics

- `recognition_confidence` = `sub_label_score` **only** (face recognition).
- `detection_confidence` = `after.score` (object/person detection). `after.top_score` is not
  used as the canonical detection field and is never a fallback.
- A score is valid iff it is a **finite real number and not a bool** (bool rejected; NaN/inf
  rejected).
- **Missing-recognition-score fail-closed rule:** if `sub_label` is present but
  `sub_label_score` is missing/null/invalid → `RECOGNITION_FAILURE`, `known=false`. The
  detection score is **never** substituted, and no confidence is invented. (Rationale:
  FR-006 / constitution II.2 — prefer no-trust over a low/unknown-confidence known.)

## Field rules (summary)

| Outcome | raw_identity | identity | person_uuid | relationship | enabled | recognition_conf | known |
|---|---|---|---|---|---|---|---|
| IDENTITY_KNOWN | sub_label | display_name | uuid | relationship | true | sub_label_score | true |
| IDENTITY_UNKNOWN | null | null | null | null | null | null | false |
| IDENTITY_DISABLED | sub_label | null | null | null | false | preserved | false |
| IDENTITY_UNMAPPED | sub_label | null | null | null | null | preserved | false |
| MAPPING_UNAVAILABLE | sub_label* | null | null | null | null | preserved* | false |
| RECOGNITION_FAILURE | sub_label*/null | null | null | null | null | null | false |
| IGNORED_NON_PERSON | null | null | null | null | null | null | false |

`detection_confidence` is `after.score` when valid, else null, across all outcomes.
