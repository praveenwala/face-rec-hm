# Contract: Relationship Mapping File Schema

The homeowner-maintained, gitignored file at `home-assistant/helpers/relationship_mapping.yaml`
(research decision #6). A committed `relationship_mapping.yaml.example` documents this shape
with placeholder data — never real household data.

## Schema

```yaml
people:
  <identity_name>:                # MUST exactly match the enrolled name Frigate reports as
                                   # sub_label (Known Identity.name — FR-031, unique)
    relationship: <category>      # optional — one of: Family | Friend | Neighbor | Other Known
                                   # omitted entirely when no category is assigned (FR-008 is
                                   # optional; US3 acceptance scenario 2)
```

## Example (`relationship_mapping.yaml.example`)

```yaml
people:
  Chandra:
    relationship: Family
  John:
    relationship: Neighbor
  Alex:
    relationship: Friend
  Vendor1:
    relationship: Other Known
  Sam:
    # no relationship key: recognized identity is reported without inventing a category
```

## Validation rules

- `<identity_name>` keys MUST be unique within the file (YAML mapping keys are inherently
  unique; a duplicate key is a file error, not a valid "two people same name" case — FR-031
  requires uniqueness be enforced at enrollment time, upstream of this file).
- `relationship`, when present, MUST be one of exactly: `Family`, `Friend`, `Neighbor`,
  `Other Known` (FR-009). Any other value is a configuration error the HA automation should
  surface rather than silently accept (constitution III.2 — the mapping must be explicit).
- This file MUST NOT be inferred or auto-populated from recognition activity — every entry is
  something the homeowner explicitly wrote (FR-007, constitution III.2, constitution II.1).
- This file MUST stay gitignored (constitution II.4); only `relationship_mapping.yaml.example`
  is committed.
