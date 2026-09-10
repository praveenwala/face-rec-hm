"""FaceDetectionService — Phase 4, T022.

Frigate-aligned YuNet face detector (``cv2.FaceDetectorYN`` + ``facedet.onnx``)
— the Frigate-aligned ``facedet.onnx`` used by the validated local Frigate 0.17.2
environment (``frigate/data_processing/real_time/face.py``). No claim of broader
compatibility with every Frigate installation/version is made — only the locally
validated 0.17.2 environment:

- ``cv2.FaceDetectorYN.create(model, config="", input_size=(320, 320),
  score_threshold=0.5, nms_threshold=0.3)``
- dynamic ``setInputSize`` per frame, >1080-height rescale guard
- detections filtered at the app level by ``QualityConfig.min_face_detect_score``
  (0.7 — aligned with Frigate's face ``detection_threshold``)

Model provenance (see research.md and scripts/fetch_models.sh):
- app-owned copy at ``enrollment-app/data/models/facedet.onnx`` (gitignored),
  fetched from the same release the validated Frigate 0.17.2 environment uses
  (``NickM-27/facenet-onnx`` v1.0, Apache-2.0); sha256
  ``321aa5a6afabf7ecc46a3d06bfab2b579dc96eb5c3be7edd365fa04502ad9294``.

**No silent fallback (user-approved Phase 4 decision):** if the model is missing or
unloadable, detection raises ``FaceDetectorUnavailableError`` — analysis fails
cleanly rather than silently switching detectors (readiness semantics must never
change depending on which detector happened to load).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.exceptions import FaceDetectorUnavailableError


@dataclass(frozen=True)
class FaceDetection:
    """A single detected face (geometry + detector confidence)."""

    x: int
    y: int
    width: int
    height: int
    score: float

    @property
    def area(self) -> int:
        return self.width * self.height


class FaceDetectionService:
    # Loaded detectors are cached per model path so repeated uploads/analyses do not
    # re-create the ONNX session each time.
    _detector_cache: dict[str, object] = {}

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._detector = None  # lazy — opencv/model only touched on first use

    # ---- loading --------------------------------------------------------------

    def _load(self) -> None:
        try:
            import cv2
        except ImportError as exc:  # pragma: no cover — opencv is a hard dependency
            raise FaceDetectorUnavailableError(
                "OpenCV is not installed (opencv-python-headless is required)"
            ) from exc

        path = self._settings.facedet_model_path
        key = str(path)
        if key in self._detector_cache:
            self._detector = self._detector_cache[key]
            return

        if not path.exists():
            raise FaceDetectorUnavailableError(
                f"Face detection model not found at {path} — "
                "run scripts/fetch_models.sh to download it into the app's private cache"
            )

        q = self._settings.quality
        try:
            detector = cv2.FaceDetectorYN.create(
                str(path),
                config="",
                input_size=(q.detect_input_size, q.detect_input_size),
                score_threshold=q.cv_score_threshold,
                nms_threshold=q.cv_nms_threshold,
            )
        except Exception as exc:
            raise FaceDetectorUnavailableError(
                f"Failed to load face detection model from {path}: {exc}"
            ) from exc
        self._detector_cache[key] = detector
        self._detector = detector

    # ---- detection ------------------------------------------------------------

    def detect(self, image_bgr) -> list[FaceDetection]:
        """Detect faces in a BGR image (OpenCV convention).

        Returns every detection above ``QualityConfig.min_face_detect_score``
        (Frigate-aligned). Raises ``FaceDetectorUnavailableError`` if the model
        cannot be loaded — never falls back to another detector.
        """
        if self._detector is None:
            self._load()

        import cv2

        q = self._settings.quality
        height, width = image_bgr.shape[:2]
        scale = 1.0
        if height > q.max_detection_height:
            # Frigate's guard: YuNet fails at extreme resolutions; rescale keeping detail.
            scale = q.max_detection_height / height
            image_bgr = cv2.resize(
                image_bgr, (int(scale * width), q.max_detection_height)
            )

        self._detector.setInputSize((image_bgr.shape[1], image_bgr.shape[0]))
        _, faces = self._detector.detect(image_bgr)
        if faces is None:
            return []

        results: list[FaceDetection] = []
        for f in faces:
            score = float(f[-1])
            if score < q.min_face_detect_score:
                continue
            x = int(max(f[0], 0) / scale)
            y = int(max(f[1], 0) / scale)
            w = int(f[2] / scale)
            h = int(f[3] / scale)
            results.append(FaceDetection(x=x, y=y, width=w, height=h, score=score))
        return results