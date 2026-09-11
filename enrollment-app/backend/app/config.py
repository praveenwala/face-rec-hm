"""Application configuration (Feature 002).

Private runtime data lives under ``enrollment-app/data/`` by default and can be
overridden with the ``ENROLLMENT_DATA_DIR`` environment variable (used by tests and
by anyone who wants the data elsewhere). Everything under the data dir is gitignored
(constitution II.4/II.5) — never commit anything under it.

Phase 6 (Frigate enrollment) adds runtime settings on the SAME ``Settings`` object.
The enrollment feature flag defaults **OFF**: while off, the enrollment machinery
performs zero mutating Frigate requests (see ``frigate_service`` / ``enrollment``).
Secrets (Frigate credentials) are sourced from the environment only and never
hardcoded or logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

APP_VERSION = "0.2.0+phase6"

# enrollment-app/data  (this file lives at enrollment-app/backend/app/config.py)
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# spec FR-004 / FR-009 — user-supplied metadata only, never inferred from appearance.
RELATIONSHIPS: tuple[str, ...] = ("Family", "Friend", "Neighbor", "Other Known")

# contracts/photo-quality.md — initial, conservative, explicitly NOT tuned.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class QualityConfig:
    """Phase 4 quality thresholds — contracts/photo-quality.md defaults.

    Initial conservative baselines, explicitly NOT claimed as tuned (same stance as
    feature 001's recognition thresholds at T033). Tunable after validation against
    real household photos; any tuning MUST be recorded in the audit log (per contract).
    Detector parameters match Frigate 0.17.2's face detection exactly
    (frigate/data_processing/real_time/face.py).
    """

    # face-size checks (face box vs image)
    min_face_area_ratio: float = 0.01
    min_face_width_ratio: float = 0.08
    min_face_height_ratio: float = 0.08
    # detector: score filter aligned with Frigate's face detection_threshold (0.7)
    min_face_detect_score: float = 0.7
    # sharpness / brightness (measured over the face crop)
    min_sharpness_laplacian: float = 40.0
    brightness_min: float = 40.0
    brightness_max: float = 220.0
    # cv2.FaceDetectorYN.create params (Frigate-aligned)
    detect_input_size: int = 320
    cv_score_threshold: float = 0.5
    cv_nms_threshold: float = 0.3
    # Frigate rescale guard for very tall images
    max_detection_height: int = 1080

    # Phase 5 — duplicate handling (contracts/photo-quality.md):
    min_approved_suitable: int = 5  # readiness gate: >= 5 approved suitable non-duplicate photos
    dup_hash_distance: int = 8  # pHash hamming distance → NEAR_DUPLICATE advisory (advisory only in MVP)
    dup_hash_size: int = 16  # pHash 16x16 (research.md #5)
    dup_hash_highfreq: int = 4  # pHash high-frequency factor (research.md #5)


@dataclass(frozen=True)
class FrigateConfig:
    """Phase 6 Frigate management-API settings (resolved from the environment).

    The single source of truth for whether enrollment mutations are allowed is
    ``enrollment_enabled`` — default **False**. Credentials come from the
    environment only; they are never committed and never logged.
    """

    enrollment_enabled: bool = False
    api_url: str = "http://127.0.0.1:5001"
    auth_username: str = ""
    auth_password: str = ""
    http_timeout_seconds: float = 30.0
    http_connect_timeout_seconds: float = 10.0
    tls_verify: bool = True

    @property
    def auth_configured(self) -> bool:
        return bool(self.auth_username and self.auth_password)


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings resolved once at app creation."""

    data_dir: Path
    frigate: FrigateConfig = field(default_factory=FrigateConfig)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def people_root(self) -> Path:
        return self.data_dir / "people"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def facedet_model_path(self) -> Path:
        """App-owned YuNet model (gitignored runtime cache; scripts/fetch_models.sh)."""
        return self.models_dir / "facedet.onnx"

    @property
    def relationships(self) -> tuple[str, ...]:
        return RELATIONSHIPS

    @property
    def max_upload_bytes(self) -> int:
        return MAX_UPLOAD_BYTES

    @property
    def quality(self) -> QualityConfig:
        return QualityConfig()

    # ---- Phase 6 convenience accessors (delegate to self.frigate) --------------
    @property
    def frigate_enrollment_enabled(self) -> bool:
        return self.frigate.enrollment_enabled

    @property
    def frigate_api_url(self) -> str:
        return self.frigate.api_url


def _load_frigate_config() -> FrigateConfig:
    return FrigateConfig(
        # Feature 002 Phase 6 gate — defaults OFF. While OFF, the enrollment machinery
        # MUST NOT perform any mutating Frigate request, even if everything else is ready.
        # Do NOT flip this default without explicit authorization.
        enrollment_enabled=_env_flag("FRIGATE_ENROLLMENT_ENABLED", default=False),
        # Convenience default for local dev/harness only; NOT a claim that the POC
        # binding (0.0.0.0:5001) is production-safe.
        api_url=os.environ.get("FRIGATE_API_URL", "http://127.0.0.1:5001").strip()
        or "http://127.0.0.1:5001",
        # Secrets — runtime only, never stored in source, never logged.
        auth_username=os.environ.get("FRIGATE_AUTH_USERNAME", "").strip(),
        auth_password=os.environ.get("FRIGATE_AUTH_PASSWORD", "").strip(),
        http_timeout_seconds=float(
            os.environ.get("FRIGATE_HTTP_TIMEOUT_SECONDS", "30.0").strip() or "30.0"
        ),
        http_connect_timeout_seconds=float(
            os.environ.get("FRIGATE_HTTP_CONNECT_TIMEOUT_SECONDS", "10.0").strip() or "10.0"
        ),
        # Strict TLS by default; an internal-CA/loopback setup may override explicitly.
        tls_verify=os.environ.get("FRIGATE_TLS_VERIFY", "true").strip().lower()
        not in ("0", "false", "no", "off"),
    )


def load_settings(data_dir: Path | None = None) -> Settings:
    if data_dir is not None:
        resolved = Path(data_dir)
    else:
        resolved = Path(os.environ.get("ENROLLMENT_DATA_DIR", DEFAULT_DATA_DIR))
    return Settings(data_dir=resolved, frigate=_load_frigate_config())
