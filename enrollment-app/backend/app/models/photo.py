"""EnrollmentPhoto model (data-model.md).

Raw image bytes never enter the database — only metadata plus a storage_path into the
private filesystem (spec FR-010). Quality status/reasons are the canonical strings from
``enums.py``; measurements are kept separate from derived judgments (FR-014).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EnrollmentPhoto(Base):
    __tablename__ = "enrollment_photos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    person_id: Mapped[str] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    face_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    face_size_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    sharpness: Mapped[float | None] = mapped_column(Float, nullable=True)
    brightness: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rejection_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    measurements: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enrolled_in_frigate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    duplicate_group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)