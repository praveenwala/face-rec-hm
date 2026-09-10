"""Person model (data-model.md).

Identity rules: ``id`` is a stable UUID used everywhere (API + filesystem); display
name is editable metadata and is never an identifier; ``frigate_identity_name`` stays
NULL until Phase 6 enrollment and is never changed by a display-name rename.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Person(Base):
    __tablename__ = "people"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    frigate_identity_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True
    )
    relationship: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enrollment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT"
    )
    representative_photo_id: Mapped[str | None] = mapped_column(
        ForeignKey("enrollment_photos.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )