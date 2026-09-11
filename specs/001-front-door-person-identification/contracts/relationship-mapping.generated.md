# Generated Relationship Mapping — HA-consumable artifacts (T034-B / T034-C1)

The Feature 002 **enrollment database is the single source of truth** for identity
metadata (person UUID, display name, `frigate_identity_name`, relationship, enabled).
The mapping artifacts below are **derived, read-only exports** — neither JSON nor YAML is
authoritative.

## Artifacts (both private, gitignored)

| Path | Purpose |
|---|---|
| `home-assistant/helpers/relationship_mapping.generated.json` | tooling/tests; deterministic |
| `home-assistant/helpers/relationship_mapping.generated.yaml` | Home Assistant `!include` consumption |

Both are generated from the same validated canonical document
(`build_entries` → `build_document` → `render_json` / `render_yaml`). They are logically
identical (proven by parity tests). YAML exists only because HA/Jinja cannot read arbitrary
JSON at runtime.

## Schema (version 1)

```yaml
schema_version: 1
identities:
  "<frigate_identity_name>":        # key = what Frigate reports as sub_label (NOT display_name)
    person_uuid: "<uuid>"
    display_name: "<editable display name>"
    relationship: "Family"          # one of: Family | Friend | Neighbor | Other Known
    enabled: true                   # disabled enrolled identities are RETAINED with enabled: false
```

All string scalars are emitted double-quoted (safe for apostrophes, colons, `#`, Unicode,
whitespace, and boolean/null/numeric-looking strings). `schema_version` and `enabled` are
unquoted (integer / boolean).

## Intended Home Assistant include shape (T034-C2+, NOT wired in C1)

The generated YAML is designed to be loaded into a Jinja-accessible variable via an
`!include`, e.g. inside the future MQTT-trigger enrichment automation:

```yaml
# automations.yaml (future C2/C3 — illustrative only; not applied in C1)
- id: front_door_person_enrichment
  trigger:
    - platform: mqtt
      topic: frigate/events
  variables:
    relationship_mapping: !include helpers/relationship_mapping.generated.yaml
  # ... Jinja then looks up trigger.payload_json.after.sub_label in
  #     relationship_mapping.identities to resolve identity/relationship/enabled ...
```

(The exact wiring — `variables:` vs a `homeassistant.packages` template — is decided and
implemented in T034-C2; C1 only proves the artifact format and parses it with a real YAML
parser.)

## Update workflow

1. Change identity data in Feature 002 (enrollment app) — the source of truth.
2. Run the read-only exporter: `python -m app.tools.relationship_export --format both`
   (or `--format yaml`). Read-only DB; deterministic; atomic write; no network/daemon/HA/
   Frigate call.
3. The generated private artifacts are updated in place (gitignored).
4. Home Assistant picks up the change on the next config/automation reload or restart
   (T034-C2+). No watcher, no long-running service.

**Rollback**: keep the previous generated file; restore it and reload. The atomic write
guarantees the target is never left partial.
