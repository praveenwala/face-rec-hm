"""Append-only audit log (spec FR-031, data-model.md).

Records administrative actions with structured details. Never accepts image bytes or
secrets — details must be plain JSON-serializable metadata.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLogEntry
from app.models.enums import AuditAction


class AuditService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        action: AuditAction,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            action=action.value,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
        self._session.add(entry)
        self._session.flush()
        return entry