"""Relationship-enrichment mapping export (Feature 001 T034-B).

Generates a PRIVATE, gitignored mapping artifact for Home Assistant to consume, derived
from the Feature 002 enrollment database (the single source of truth). This is a one-shot,
READ-ONLY export utility:

  - reads the enrollment DB only (no network, no daemon, no scheduler, no HA call, no
    Frigate call, no DB mutation)
  - keyed by ``frigate_identity_name`` (what Frigate reports as sub_label — NOT display_name)
  - includes only ENROLLED persons with a non-null frigate_identity_name and an explicit,
    valid relationship
  - preserves ``enabled`` (disabled identities are kept with enabled=false, never silently
    omitted — HA must distinguish disabled-known from unmapped)
  - fail-closed validation: duplicate identity name / missing uuid / missing display_name /
    missing or invalid relationship => raises, writes NOTHING
  - deterministic ordering (sorted by frigate_identity_name)
  - atomic write (temp file in the same dir, then os.replace)

Output format: JSON (stdlib-only; no new dependency; deterministic; HA-template readable).
The runtime output path contains real household identity metadata and is gitignored.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.config import RELATIONSHIPS, Settings, load_settings
from app.db import make_session_factory
from app.models.enums import EnrollmentStatus
from app.models.person import Person

SCHEMA_VERSION = 1
ALLOWED_RELATIONSHIPS = tuple(RELATIONSHIPS)  # Family | Friend | Neighbor | Other Known

# Default private, gitignored output (see .gitignore). Deterministic, documented path.
DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parents[4]  # enrollment-app/backend/app/tools -> repo root
    / "home-assistant"
    / "helpers"
    / "relationship_mapping.generated.json"
)


class RelationshipExportError(ValueError):
    """Raised on any validation failure. When raised, NO output file is written."""


@dataclass(frozen=True)
class ExportEntry:
    frigate_identity_name: str
    person_uuid: str
    display_name: str
    relationship: str
    enabled: bool


def _candidate_persons(session: Session) -> list[Person]:
    """ENROLLED persons with a non-null frigate_identity_name. Read-only query."""
    return (
        session.query(Person)
        .filter(Person.enrollment_status == EnrollmentStatus.ENROLLED.value)
        .filter(Person.frigate_identity_name.isnot(None))
        .all()
    )


def build_entries(session: Session) -> list[ExportEntry]:
    """Validate candidates and return deterministically-ordered entries.

    Fail-closed: any ambiguity (duplicate identity name, missing/invalid fields) raises
    RelationshipExportError and produces no partial result.
    """
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
    # Deterministic ordering by identity name.
    entries.sort(key=lambda e: e.frigate_identity_name)
    return entries


def build_document(entries: Iterable[ExportEntry], *, generated_at: str | None = None) -> dict[str, Any]:
    """Build the serializable mapping document. ``generated_at`` is injectable (and omitted
    when None) so equality-based tests stay deterministic."""
    doc: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
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


def _atomic_write_json(target: Path, doc: dict[str, Any]) -> None:
    """Write JSON atomically: temp file in the same directory, then os.replace.

    If serialization or write fails, the target is never left partial (the temp file is
    removed and the original target is untouched)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".relmap.", suffix=".tmp", dir=str(target.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)  # atomic on same filesystem
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def export_mapping(
    session: Session,
    output_path: Path | None = None,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Validate + write the mapping atomically. Returns the written document.

    Read-only w.r.t. the DB. Raises RelationshipExportError on validation failure (no file
    written). Never contacts HA/Frigate/network.
    """
    entries = build_entries(session)  # validates (may raise before any write)
    doc = build_document(entries, generated_at=generated_at)
    _atomic_write_json(output_path or DEFAULT_OUTPUT_PATH, doc)
    return doc


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI wrapper
    """One-shot CLI: `python -m app.tools.relationship_export`.

    Prints only metadata counts (never identity contents) to keep runtime output private.
    """
    settings: Settings = load_settings()
    session_factory = make_session_factory(settings.db_path)
    with session_factory() as session:
        entries = build_entries(session)
        export_mapping(session, generated_at=None)
    enabled = sum(1 for e in entries if e.enabled)
    print(
        f"relationship mapping exported: {len(entries)} identities "
        f"({enabled} enabled, {len(entries) - enabled} disabled) "
        f"-> {DEFAULT_OUTPUT_PATH}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
