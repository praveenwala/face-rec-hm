"""Relationship-enrichment mapping export (Feature 001 T034-B/T034-C1).

Generates PRIVATE, gitignored mapping artifacts for Home Assistant to consume, derived
from the Feature 002 enrollment database (the SINGLE SOURCE OF TRUTH). One-shot, READ-ONLY:

  - reads the enrollment DB only (no network, no daemon, no scheduler, no HA call, no
    Frigate call, no DB mutation)
  - keyed by ``frigate_identity_name`` (what Frigate reports as sub_label — NOT display_name)
  - includes only ENROLLED persons with a non-null frigate_identity_name and an explicit,
    valid relationship
  - preserves ``enabled`` (disabled identities kept with enabled=false, never omitted)
  - fail-closed validation (duplicate identity / missing uuid|display_name|relationship /
    invalid relationship => raises, writes NOTHING)
  - deterministic ordering (sorted by frigate_identity_name)
  - atomic write (temp file in same dir, then os.replace)

Both JSON and YAML are DERIVED artifacts of the same validated canonical mapping
(``build_entries`` -> ``build_document`` -> {json,yaml} serializer). Neither file is the
source of truth; the enrollment DB is. JSON is convenient for tooling/tests; YAML exists
for Home Assistant-native ``!include`` consumption (HA/Jinja cannot read arbitrary JSON at
runtime). Both runtime artifacts contain real household metadata and are gitignored.

YAML serialization (T034-C1): a small, SAFE serializer for exactly this fixed schema —
every string is emitted as a YAML double-quoted scalar with full escaping, so apostrophes,
colons, '#', Unicode, leading/trailing whitespace, and boolean/null/numeric-looking strings
are preserved as strings (no ambiguity). No new runtime dependency is added. The output is
round-trip validated against a real YAML parser in tests.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from sqlalchemy.orm import Session

from app.config import RELATIONSHIPS, Settings, load_settings
from app.db import make_session_factory
from app.models.enums import EnrollmentStatus
from app.models.person import Person

SCHEMA_VERSION = 1
ALLOWED_RELATIONSHIPS = tuple(RELATIONSHIPS)  # Family | Friend | Neighbor | Other Known

_HELPERS_DIR = (
    Path(__file__).resolve().parents[4]  # enrollment-app/backend/app/tools -> repo root
    / "home-assistant"
    / "helpers"
)
DEFAULT_JSON_PATH = _HELPERS_DIR / "relationship_mapping.generated.json"
DEFAULT_YAML_PATH = _HELPERS_DIR / "relationship_mapping.generated.yaml"


class RelationshipExportError(ValueError):
    """Raised on any validation failure. When raised, NO output file is written."""


@dataclass(frozen=True)
class ExportEntry:
    frigate_identity_name: str
    person_uuid: str
    display_name: str
    relationship: str
    enabled: bool


# ---------------------------------------------------------------------------
# Canonical mapping (single validated pipeline shared by all serializers)
# ---------------------------------------------------------------------------


def _candidate_persons(session: Session) -> list[Person]:
    """ENROLLED persons with a non-null frigate_identity_name. Read-only query."""
    return (
        session.query(Person)
        .filter(Person.enrollment_status == EnrollmentStatus.ENROLLED.value)
        .filter(Person.frigate_identity_name.isnot(None))
        .all()
    )


def build_entries(session: Session) -> list[ExportEntry]:
    """Validate candidates and return deterministically-ordered entries. Fail-closed."""
    entries: list[ExportEntry] = []
    seen_names: set[str] = set()
    for p in _candidate_persons(session):
        name = (p.frigate_identity_name or "").strip()
        if not name:
            raise RelationshipExportError(
                f"person {p.id}: ENROLLED but frigate_identity_name is empty"
            )
        if not (p.id or "").strip():
            raise RelationshipExportError(f"identity {name!r}: missing person UUID")
        if not (p.display_name or "").strip():
            raise RelationshipExportError(f"identity {name!r}: missing display_name")
        rel = (p.relationship or "").strip()
        if not rel:
            raise RelationshipExportError(
                f"identity {name!r}: missing relationship (fail-closed)"
            )
        if rel not in ALLOWED_RELATIONSHIPS:
            raise RelationshipExportError(
                f"identity {name!r}: invalid relationship {rel!r} "
                f"(allowed: {', '.join(ALLOWED_RELATIONSHIPS)})"
            )
        if name in seen_names:
            raise RelationshipExportError(
                f"duplicate frigate_identity_name {name!r}: refusing to overwrite"
            )
        seen_names.add(name)
        entries.append(
            ExportEntry(
                frigate_identity_name=name,
                person_uuid=p.id,
                display_name=p.display_name,
                relationship=rel,
                enabled=bool(p.enabled),
            )
        )
    entries.sort(key=lambda e: e.frigate_identity_name)  # deterministic
    return entries


def build_document(entries: Iterable[ExportEntry], *, generated_at: str | None = None) -> dict[str, Any]:
    """The single canonical mapping document; both serializers render THIS."""
    doc: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,  # integer 1
        "identities": {
            e.frigate_identity_name: {
                "person_uuid": e.person_uuid,
                "display_name": e.display_name,
                "relationship": e.relationship,
                "enabled": e.enabled,
            }
            for e in entries
        },
    }
    if generated_at is not None:
        doc["generated_at"] = generated_at
    return doc


# ---------------------------------------------------------------------------
# Serializers (JSON, YAML) — both render the same canonical document
# ---------------------------------------------------------------------------


def render_json(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _yaml_double_quote(s: str) -> str:
    """Emit a YAML double-quoted scalar with full escaping.

    Double-quoting forces string type, so colons, '#', apostrophes, whitespace, and
    boolean/null/numeric-looking values round-trip as strings unambiguously.
    """
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif o < 0x20:  # other control chars -> \xNN
            out.append(f"\\x{o:02x}")
        else:
            out.append(ch)  # printable/Unicode kept as-is (UTF-8 file)
    out.append('"')
    return "".join(out)


def render_yaml(doc: dict[str, Any]) -> str:
    """Deterministic YAML for the fixed relationship-mapping schema.

    Only the shapes this document uses are handled (top-level scalars + a nested
    identities map of string->{4 fields}); it is not a general YAML emitter.
    """
    lines: list[str] = []
    # top-level scalars in a stable order (schema_version first, generated_at if present)
    lines.append(f"schema_version: {int(doc['schema_version'])}")
    if "generated_at" in doc:
        lines.append(f"generated_at: {_yaml_double_quote(str(doc['generated_at']))}")
    lines.append("identities:")
    identities = doc.get("identities", {})
    if not identities:
        lines[-1] = "identities: {}"
    else:
        for key in sorted(identities):  # deterministic ordering
            entry = identities[key]
            lines.append(f"  {_yaml_double_quote(key)}:")
            lines.append(f"    person_uuid: {_yaml_double_quote(str(entry['person_uuid']))}")
            lines.append(f"    display_name: {_yaml_double_quote(str(entry['display_name']))}")
            lines.append(f"    relationship: {_yaml_double_quote(str(entry['relationship']))}")
            lines.append(f"    enabled: {'true' if entry['enabled'] else 'false'}")
    return "\n".join(lines) + "\n"


_RENDERERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "json": render_json,
    "yaml": render_yaml,
}
_DEFAULT_PATHS: dict[str, Path] = {
    "json": DEFAULT_JSON_PATH,
    "yaml": DEFAULT_YAML_PATH,
}


# ---------------------------------------------------------------------------
# Atomic write + export
# ---------------------------------------------------------------------------


def _atomic_write_text(target: Path, text: str) -> None:
    """Write text atomically: temp file in the same dir, then os.replace. On failure the
    target is untouched and the temp file removed (no partial output)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".relmap.", suffix=".tmp", dir=str(target.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def export_mapping(
    session: Session,
    output_path: Path | None = None,
    *,
    fmt: str = "json",
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Validate + atomically write the mapping in ``fmt`` (json|yaml). Returns the canonical
    document. Read-only DB; raises RelationshipExportError on validation failure (no write)."""
    if fmt not in _RENDERERS:
        raise ValueError(f"unknown format {fmt!r} (expected one of: {', '.join(_RENDERERS)})")
    entries = build_entries(session)  # validates (may raise before any write)
    doc = build_document(entries, generated_at=generated_at)
    # Dispatch by name (module-level) so tests can monkeypatch a renderer to inject failures.
    renderer = render_yaml if fmt == "yaml" else render_json
    _atomic_write_text(output_path or _DEFAULT_PATHS[fmt], renderer(doc))
    return doc


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI wrapper
    """One-shot CLI. `--format json|yaml|both` (default json to preserve T034-B callers).
    Prints only metadata counts (never identity contents)."""
    parser = argparse.ArgumentParser(description="Export the relationship-enrichment mapping.")
    parser.add_argument("--format", choices=["json", "yaml", "both"], default="json")
    args = parser.parse_args(argv)

    settings: Settings = load_settings()
    session_factory = make_session_factory(settings.db_path)
    with session_factory() as session:
        entries = build_entries(session)  # validate once, up-front
        formats = ["json", "yaml"] if args.format == "both" else [args.format]
        for fmt in formats:
            export_mapping(session, fmt=fmt, generated_at=None)
    enabled = sum(1 for e in entries if e.enabled)
    print(
        f"relationship mapping exported ({args.format}): {len(entries)} identities "
        f"({enabled} enabled, {len(entries) - enabled} disabled)"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
