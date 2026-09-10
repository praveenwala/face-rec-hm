"""PhotoService — Phase 3 photo ingestion and lifecycle (T016–T019).

Scope (user-approved Phase 3 boundary):
- Ingestion validation ONLY: upload size limit, content sniffing (magic bytes, never
  extension alone), Pillow decode, EXIF orientation recorded, dimensions/mime recorded.
  NO face detection, NO sharpness/brightness, NO duplicate detection, NO enrollment —
  those are Phase 4/5/6. Every accepted photo stays quality_status=PENDING,
  approved=False, enrolled_in_frigate=False (FR-019/FR-022).
- Originals are stored byte-for-byte under data/people/<uuid>/original/; the stored
  filename is a random UUID (never the user's filename), so display-name renames and
  weird/duplicate/traversal filenames can never affect the filesystem (FR-010/FR-011).
- Multi-file upload: one result object per file (accepted or rejected with an explicit
  reason); one bad file never corrupts the rest of the batch.
- Application upload allowlist is EXACTLY JPEG/PNG/WEBP (user-approved), decided by
  decoded/sniffed content — never by filename extension. Valid GIF/BMP/TIFF/other
  Pillow-decodable formats are rejected with UNSUPPORTED_FORMAT; HEIC/HEIF is detected by
  content and rejected with UNSUPPORTED_FORMAT (normalization deferred pending explicit
  approval — no silent normalization).
- No endpoint exposes absolute storage paths; responses carry metadata + API URLs only.
"""

from __future__ import annotations

import io
import logging

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.config import Settings
from app.exceptions import PhotoNotFoundError, StorageError
from app.models.enums import AuditAction, QualityStatus, RejectionReason
from app.models.photo import EnrollmentPhoto
from app.services.audit_service import AuditService
from app.services.person_service import PersonService
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)

_THUMBNAIL_MAX = 300
_THUMBNAIL_JPEG_QUALITY = 80

# Content sniffing — mime is decided by magic bytes, never by filename extension.
# Application allowlist: EXACTLY JPEG/PNG/WEBP (user-approved Phase 3 decision). GIF/BMP/
# TIFF and other Pillow-decodable formats are valid images but are rejected with
# UNSUPPORTED_FORMAT for the predictable enrollment-media workflow.
_ALLOWED_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}

_HEIC_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1")


def _sniff_kind(data: bytes) -> str | None:
    """Return a Pillow-style format name from magic bytes, or None if unrecognized."""
    if data[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "GIF"
    if data[:2] == b"BM":
        return "BMP"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "TIFF"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in _HEIC_BRANDS:
        return "HEIC"
    return None


class PhotoService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._storage = StorageService(settings)
        self._audit = AuditService(session)
        self._persons = PersonService(session)

    # ---- upload --------------------------------------------------------------

    def upload_files(self, person_id: str, payloads: list[tuple[str, bytes]]) -> list[dict]:
        """Ingest a batch of files. Returns one result object per file.

        ``payloads`` is a list of (original_filename, bytes). A file that fails
        ingestion is rejected with an explicit rejection_reason — never silently
        dropped, and never allowed to abort the rest of the batch.
        """
        self._persons.get(person_id)  # raises PersonNotFoundError → 404
        results: list[dict] = []
        for original_name, data in payloads:
            results.append(self._ingest_one(person_id, original_name, data))
        return results

    def _ingest_one(self, person_id: str, original_name: str, data: bytes) -> dict:
        max_bytes = self._settings.max_upload_bytes
        if len(data) > max_bytes:
            return self._rejected(original_name, RejectionReason.FILE_TOO_LARGE, {"max_bytes": max_bytes})

        kind = _sniff_kind(data)
        if kind is None:
            return self._rejected(original_name, RejectionReason.UNSUPPORTED_FORMAT)
        if kind == "HEIC":
            # HEIC/HEIF stays unsupported — no silent normalization (deferred pending
            # explicit approval). Never silently accepted, never a decode failure.
            return self._rejected(
                original_name,
                RejectionReason.UNSUPPORTED_FORMAT,
                {"note": "HEIC/HEIF is not supported; convert to JPEG/PNG/WEBP before uploading"},
            )
        if kind not in _ALLOWED_FORMATS:
            # Recognized content outside the allowlist (GIF/BMP/TIFF/…) — valid image but
            # rejected for this workflow; the allowlist is content-based, not extension-based.
            return self._rejected(
                original_name,
                RejectionReason.UNSUPPORTED_FORMAT,
                {"detected_format": kind},
            )

        try:
            with Image.open(io.BytesIO(data)) as img:
                img.load()  # force full decode; raises for corrupt/truncated payloads
                pillow_format = (img.format or "").upper()
                if pillow_format not in _ALLOWED_FORMATS:
                    # Decoded format must also be in the allowlist (both sniff and decode
                    # must agree); a spoofed signature can never widen the allowlist.
                    return self._rejected(
                        original_name,
                        RejectionReason.UNSUPPORTED_FORMAT,
                        {"detected_format": pillow_format or None},
                    )
                orientation = img.getexif().get(0x0112)
                transposed = ImageOps.exif_transpose(img)
                width, height = transposed.size
                thumbnail = self._make_thumbnail(transposed)
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
            logger.info("Photo %r rejected: decode failed (%s)", original_name, type(exc).__name__)
            # Recognized signature but Pillow can't decode → corrupt/truncated.
            return self._rejected(original_name, RejectionReason.MEDIA_DECODE_FAILURE)

        try:
            original_path = self._storage.write_original(person_id, original_name, data)
            stored_filename = original_path.name
            storage_path = str(original_path.relative_to(self._storage.root))
        except StorageError as exc:
            logger.error("Storage failure during photo ingestion: %s", exc)
            return self._rejected(original_name, RejectionReason.STORAGE_FAILURE)

        return self._finalize_photo(
            person_id,
            original_name,
            data,
            stored_filename,
            storage_path,
            _ALLOWED_FORMATS[pillow_format],
            width,
            height,
            orientation,
            thumbnail,
        )

    def _finalize_photo(
        self,
        person_id: str,
        original_name: str,
        data: bytes,
        stored_filename: str,
        storage_path: str,
        mime_type: str,
        width: int,
        height: int,
        orientation: int | None,
        thumbnail: bytes,
    ) -> dict:
        photo = EnrollmentPhoto(
            person_id=person_id,
            original_filename=original_name,
            stored_filename=stored_filename,
            storage_path=storage_path,
            mime_type=mime_type,
            width=width,
            height=height,
            file_size=len(data),
            # Phase 3 fields stay at their defaults — never fabricated (FR-012 etc.):
            quality_status=QualityStatus.PENDING.value,
            approved=False,
            enrolled_in_frigate=False,
            measurements={"orientation": orientation} if orientation is not None else {},
        )
        self._session.add(photo)
        try:
            self._session.flush()  # assigns photo.id
            self._storage.write_thumbnail(person_id, photo.id, thumbnail)
            self._audit.record(
                AuditAction.PHOTO_UPLOADED,
                entity_type="photo",
                entity_id=photo.id,
                details={
                    "person_id": person_id,
                    "mime_type": mime_type,
                    "width": width,
                    "height": height,
                    "file_size": len(data),
                },
            )
            self._session.commit()
        except StorageError:
            self._session.rollback()
            self._storage.delete_photo_files(person_id, stored_filename, photo.id)
            return self._rejected(original_name, RejectionReason.STORAGE_FAILURE)
        except Exception:
            self._session.rollback()
            self._storage.delete_photo_files(person_id, stored_filename, photo.id)
            raise

        return {
            "photo_id": photo.id,
            "original_filename": original_name,
            "quality_status": photo.quality_status,
            "rejection_reason": None,
            "measurements": photo.measurements,
            "approved": photo.approved,
        }

    @staticmethod
    def _rejected(original_name: str, reason: RejectionReason, extra: dict | None = None) -> dict:
        return {
            "photo_id": None,
            "original_filename": original_name,
            "quality_status": None,
            "rejection_reason": reason.value,
            "measurements": extra or {},
            "approved": False,
        }

    @staticmethod
    def _make_thumbnail(img: Image.Image) -> bytes:
        work = img
        if work.mode not in ("RGB", "L"):
            work = work.convert("RGB")
        copy = work.copy()
        copy.thumbnail((_THUMBNAIL_MAX, _THUMBNAIL_MAX))
        buf = io.BytesIO()
        copy.save(buf, format="JPEG", quality=_THUMBNAIL_JPEG_QUALITY)
        return buf.getvalue()

    # ---- reads ---------------------------------------------------------------

    def list_photos(self, person_id: str) -> list[dict]:
        self._persons.get(person_id)  # 404 if person unknown
        photos = (
            self._session.query(EnrollmentPhoto)
            .filter(EnrollmentPhoto.person_id == person_id)
            .order_by(EnrollmentPhoto.created_at)
            .all()
        )
        return [self.to_summary(p) for p in photos]

    def get_photo(self, person_id: str, photo_id: str) -> dict:
        photo = self._photo_for_person(person_id, photo_id)
        return self.to_detail(photo)

    def _photo_for_person(self, person_id: str, photo_id: str) -> EnrollmentPhoto:
        photo = self._session.get(EnrollmentPhoto, photo_id)
        if photo is None or photo.person_id != person_id:
            # 404 for both unknown id and cross-person access — never leaks existence.
            raise PhotoNotFoundError(f"Photo {photo_id} not found for person {person_id}")
        return photo

    # ---- file/thumbnail serving ----------------------------------------------

    def get_original_bytes(self, person_id: str, photo_id: str) -> tuple[bytes, str]:
        photo = self._photo_for_person(person_id, photo_id)
        try:
            data = self._storage.read(photo.storage_path)
        except StorageError as exc:
            # DB row exists but the backing file is gone — explicit, safe 404.
            raise PhotoNotFoundError(
                f"Stored file for photo {photo_id} is missing",
                details={"photo_id": photo_id},
            ) from exc
        return data, photo.mime_type

    def get_thumbnail_bytes(self, person_id: str, photo_id: str) -> tuple[bytes, str]:
        self._photo_for_person(person_id, photo_id)
        try:
            data = self._storage.read_thumbnail(person_id, photo_id)
        except StorageError as exc:
            raise PhotoNotFoundError(
                f"Thumbnail for photo {photo_id} is missing",
                details={"photo_id": photo_id},
            ) from exc
        return data, "image/jpeg"

    # ---- delete ---------------------------------------------------------------

    def delete_photo(self, person_id: str, photo_id: str) -> None:
        photo = self._photo_for_person(person_id, photo_id)
        self._audit.record(
            AuditAction.PHOTO_DELETED,
            entity_type="photo",
            entity_id=photo.id,
            details={"person_id": person_id},
        )
        self._session.delete(photo)
        self._session.commit()
        # Remove all copies (original/normalized/approved) + thumbnail. Missing files
        # are fine (missing_ok) — deletion still succeeds (US2 scenario 4).
        self._storage.delete_photo_files(person_id, photo.stored_filename, photo.id)

    def delete_person_files(self, person_id: str) -> None:
        """Remove the person's whole private photo tree (person delete, Phase 3)."""
        self._storage.delete_person_files(person_id)

    # ---- response shapes ------------------------------------------------------

    def to_summary(self, photo: EnrollmentPhoto) -> dict:
        return {
            "id": photo.id,
            "person_id": photo.person_id,
            "original_filename": photo.original_filename,
            "mime_type": photo.mime_type,
            "width": photo.width,
            "height": photo.height,
            "file_size": photo.file_size,
            "quality_status": photo.quality_status,
            "approved": photo.approved,
            "rejection_reason": photo.rejection_reason,
            "enrolled_in_frigate": photo.enrolled_in_frigate,
            "thumbnail_url": f"/api/people/{photo.person_id}/photos/{photo.id}/thumbnail",
            "created_at": photo.created_at.isoformat() if photo.created_at else None,
        }

    def to_detail(self, photo: EnrollmentPhoto) -> dict:
        detail = self.to_summary(photo)
        detail.update(
            {
                "measurements": photo.measurements,
                "rejection_details": photo.rejection_details,
                "duplicate_group": photo.duplicate_group,
            }
        )
        return detail