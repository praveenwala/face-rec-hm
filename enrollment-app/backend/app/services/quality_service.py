"""PhotoQualityService — Phase 4, T023–T026.

Per-photo objective analysis pipeline (contracts/photo-quality.md), wired into
upload (automatic) and available as an explicit re-analysis action:

    stored original → safe decode → EXIF-normalized working copy (in memory) →
    face detection (Frigate-aligned YuNet) → objective measurements →
    deterministic classification → persisted metadata

Boundaries (Phase 4):
- The stored original is never modified; no normalized artifact is produced in
  this phase (HEIC normalization is deferred) — analysis works on an in-memory
  EXIF-transposed copy only.
- Classification follows the contract precedence exactly (decode → detector →
  NO_FACE → MULTIPLE_FACES → FACE_TOO_SMALL → TOO_BLURRY → exposure → SUITABLE).
- ``quality_status == SUITABLE`` never implies approval or enrollment: this
  service never touches ``approved`` / ``enrolled_in_frigate`` / identity fields.
- Detector unavailable → ``FaceDetectorUnavailableError`` propagates; the caller
  decides (upload degrades to PENDING with an explicit analysis_error; the
  re-analysis endpoint returns 503). No silent fallback, no fabricated results.
"""

from __future__ import annotations

import io
import logging

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.config import Settings
from app.exceptions import PhotoNotFoundError, StorageError
from app.models.enums import QualityStatus, RejectionReason
from app.models.photo import EnrollmentPhoto
from app.services.face_detector import FaceDetectionService
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


def _laplacian_var(gray_crop) -> float:
    """Objective blur/sharpness metric: variance of Laplacian over the face crop."""
    import cv2

    if gray_crop.size == 0:
        return 0.0
    return float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(float(value), digits)


class PhotoQualityService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._storage = StorageService(settings)
        self._detector = FaceDetectionService(settings)

    # ---- entry points ----------------------------------------------------------

    def analyze_uploaded(self, photo: EnrollmentPhoto, data: bytes) -> dict:
        """Analyze a freshly ingested photo (called during upload). Does NOT commit —
        the upload transaction commits. Never touches approval/enrollment fields."""
        result = self._analyze_bytes(data)
        self._apply_to_photo(photo, result)
        return result

    def analyze_photo(self, person_id: str, photo_id: str) -> dict:
        """Re-analyze a stored photo (explicit action). Own unit of work (commits)."""
        photo = self._session.get(EnrollmentPhoto, photo_id)
        if photo is None or photo.person_id != person_id:
            raise PhotoNotFoundError(f"Photo {photo_id} not found for person {person_id}")
        try:
            data = self._storage.read(photo.storage_path)
        except StorageError as exc:
            raise PhotoNotFoundError(
                f"Stored file for photo {photo_id} is missing",
                details={"photo_id": photo_id},
            ) from exc
        result = self._analyze_bytes(data)
        self._apply_to_photo(photo, result)
        self._session.commit()
        return result

    # ---- pipeline --------------------------------------------------------------

    def _analyze_bytes(self, data: bytes) -> dict:
        """Run the full pipeline over raw image bytes; returns a result dict.

        Raises ``FaceDetectorUnavailableError`` (propagates — caller decides).
        """
        # 1–2. safe decode (ingestion already validated; reanalysis still guards)
        try:
            with Image.open(io.BytesIO(data)) as img:
                img.load()
                orientation = img.getexif().get(0x0112)
                work = ImageOps.exif_transpose(img).convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
            return self._classify(
                QualityStatus.UNSUITABLE,
                RejectionReason.MEDIA_DECODE_FAILURE,
                measurements={"image_width": None, "image_height": None},
                rejection_details={"note": "Stored file could not be decoded"},
            )

        width, height = work.size
        image_area = width * height

        # 3. face detection (Frigate-aligned YuNet; BGR convention)
        bgr = np.array(work)[:, :, ::-1].copy()
        faces = self._detector.detect(bgr)  # raises FaceDetectorUnavailableError

        # 4. objective measurements
        face_count = len(faces)
        measurements: dict = {
            "image_width": width,
            "image_height": height,
            "face_count": face_count,
        }
        if orientation is not None:
            measurements["orientation"] = orientation

        if face_count == 0:
            return self._classify(
                QualityStatus.UNSUITABLE,
                RejectionReason.NO_FACE,
                measurements=measurements,
            )

        faces_sorted = sorted(faces, key=lambda f: f.area, reverse=True)
        primary = faces_sorted[0]
        measurements["faces"] = [
            {
                "x": f.x,
                "y": f.y,
                "width": f.width,
                "height": f.height,
                "score": _round(f.score, 3),
                "area_ratio": _round(f.area / image_area, 5),
            }
            for f in faces_sorted
        ]

        # 5. hard stop for multiple faces — never auto-select (FR-017)
        if face_count > 1:
            measurements["primary_face"] = "largest (informational only, not auto-selected)"
            return self._classify(
                QualityStatus.REVIEW_REQUIRED,
                RejectionReason.MULTIPLE_FACES,
                measurements=measurements,
                rejection_details={
                    "face_count": face_count,
                    "note": "For enrollment, use an image containing only the intended person.",
                },
            )

        # 6. single face: crop-level measurements (contract photo-quality.md)
        gray = np.array(work.convert("L"))
        x0, y0 = max(primary.x, 0), max(primary.y, 0)
        x1, y1 = min(primary.x + primary.width, width), min(primary.y + primary.height, height)
        crop = gray[y0:y1, x0:x1]
        sharpness = _laplacian_var(crop)
        brightness = float(crop.mean()) if crop.size else 0.0

        area_ratio = primary.area / image_area
        width_ratio = primary.width / width
        height_ratio = primary.height / height
        measurements.update(
            {
                "face_size_ratio": _round(area_ratio, 5),
                "face_width_ratio": _round(width_ratio, 5),
                "face_height_ratio": _round(height_ratio, 5),
                "sharpness": _round(sharpness, 2),
                "brightness": _round(brightness, 2),
                "primary_face": {
                    "x": primary.x,
                    "y": primary.y,
                    "width": primary.width,
                    "height": primary.height,
                    "score": _round(primary.score, 3),
                },
            }
        )

        q = self._settings.quality

        # 7. face too small
        if (
            area_ratio < q.min_face_area_ratio
            or width_ratio < q.min_face_width_ratio
            or height_ratio < q.min_face_height_ratio
        ):
            return self._classify(
                QualityStatus.UNSUITABLE,
                RejectionReason.FACE_TOO_SMALL,
                measurements=measurements,
                rejection_details={
                    "face_size_ratio": _round(area_ratio, 5),
                    "face_width_ratio": _round(width_ratio, 5),
                    "face_height_ratio": _round(height_ratio, 5),
                    "min_face_area_ratio": q.min_face_area_ratio,
                    "min_face_width_ratio": q.min_face_width_ratio,
                    "min_face_height_ratio": q.min_face_height_ratio,
                },
            )

        # 8. too blurry (Laplacian variance over the face crop)
        if sharpness < q.min_sharpness_laplacian:
            return self._classify(
                QualityStatus.UNSUITABLE,
                RejectionReason.TOO_BLURRY,
                measurements=measurements,
                rejection_details={
                    "sharpness": _round(sharpness, 2),
                    "min_sharpness_laplacian": q.min_sharpness_laplacian,
                },
            )

        # 9. brightness/exposure heuristics (never phrased as day/night/indoor)
        if brightness < q.brightness_min:
            return self._classify(
                QualityStatus.UNSUITABLE,
                RejectionReason.UNDEREXPOSED,
                measurements=measurements,
                rejection_details={
                    "brightness": _round(brightness, 2),
                    "brightness_min": q.brightness_min,
                },
            )
        if brightness > q.brightness_max:
            return self._classify(
                QualityStatus.UNSUITABLE,
                RejectionReason.OVEREXPOSED,
                measurements=measurements,
                rejection_details={
                    "brightness": _round(brightness, 2),
                    "brightness_max": q.brightness_max,
                },
            )

        # 10. all checks pass
        return self._classify(
            QualityStatus.SUITABLE,
            None,
            measurements=measurements,
        )

    @staticmethod
    def _classify(
        status: QualityStatus,
        reason: RejectionReason | None,
        *,
        measurements: dict,
        rejection_details: dict | None = None,
    ) -> dict:
        return {
            "quality_status": status.value,
            "rejection_reason": reason.value if reason else None,
            "rejection_details": rejection_details,
            "measurements": measurements,
        }

    # ---- persistence ------------------------------------------------------------

    def _apply_to_photo(self, photo: EnrollmentPhoto, result: dict) -> None:
        """Write analysis results to the photo row. Approval/enrollment untouched."""
        m = result["measurements"]
        photo.face_count = m.get("face_count")
        photo.face_size_ratio = m.get("face_size_ratio")
        photo.sharpness = m.get("sharpness")
        photo.brightness = m.get("brightness")
        photo.quality_status = result["quality_status"]
        photo.rejection_reason = result["rejection_reason"]
        photo.rejection_details = result["rejection_details"]
        photo.measurements = m
        # approved / enrolled_in_frigate are deliberately never touched here.