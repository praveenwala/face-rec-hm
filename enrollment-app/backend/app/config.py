"""Application configuration (Feature 002).

Private runtime data lives under ``enrollment-app/data/`` by default and can be
overridden with the ``ENROLLMENT_DATA_DIR`` environment variable (used by tests and
by anyone who wants the data elsewhere). Everything under the data dir is gitignored
(constitution II.4/II.5) — never commit anything under it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_VERSION = "0.1.0"

# enrollment-app/data  (this file lives at enrollment-app/backend/app/config.py)
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# spec FR-004 / FR-009 — user-supplied metadata only, never inferred from appearance.
RELATIONSHIPS: tuple[str, ...] = ("Family", "Friend", "Neighbor", "Other Known")

# contracts/photo-quality.md — initial, conservative, explicitly NOT tuned.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings resolved once at app creation."""

    data_dir: Path

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
    def relationships(self) -> tuple[str, ...]:
        return RELATIONSHIPS

    @property
    def max_upload_bytes(self) -> int:
        return MAX_UPLOAD_BYTES


def load_settings(data_dir: Path | None = None) -> Settings:
    if data_dir is not None:
        resolved = Path(data_dir)
    else:
        resolved = Path(os.environ.get("ENROLLMENT_DATA_DIR", DEFAULT_DATA_DIR))
    return Settings(data_dir=resolved)