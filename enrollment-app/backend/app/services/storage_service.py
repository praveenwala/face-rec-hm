"""Private filesystem storage (data-model.md, spec FR-010).

Everything is confined under the settings data dir (``enrollment-app/data/`` by
default). Person directories are named by person UUID — never by display name.
Filenames are randomized UUIDs; the original filename is metadata only.

Path traversal defense: every path is resolved and verified to stay inside the data
root before any write/read. Never trust caller-supplied names as path components.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from app.config import Settings
from app.exceptions import StorageError

_SAFE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".heic", ".heif"}


def _safe_suffix(original_name: str) -> str:
    """Return a whitelisted lowercase suffix, or '' if the name has none known."""
    suffix = Path(original_name).suffix.lower()
    return suffix if suffix in _SAFE_SUFFIXES else ""


class StorageService:
    def __init__(self, settings: Settings) -> None:
        self.root: Path = settings.data_dir
        self.people_root: Path = settings.people_root

    # -- path construction (all traversal-safe) ---------------------------------

    def resolve_inside(self, *parts: str | Path) -> Path:
        """Resolve *parts* relative to the data root, rejecting any escape."""
        candidate = self.root.joinpath(*parts)
        resolved = candidate.resolve()
        root_resolved = self.root.resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError as exc:
            raise StorageError(
                "Path escapes the private data directory",
                details={"attempted": str(candidate)},
            ) from exc
        return resolved

    def person_dir(self, person_id: str) -> Path:
        return self.resolve_inside("people", person_id)

    def original_dir(self, person_id: str) -> Path:
        return self.resolve_inside("people", person_id, "original")

    def normalized_dir(self, person_id: str) -> Path:
        return self.resolve_inside("people", person_id, "normalized")

    def approved_dir(self, person_id: str) -> Path:
        return self.resolve_inside("people", person_id, "approved")

    def thumb_dir(self, person_id: str) -> Path:
        return self.resolve_inside("people", person_id, "thumbs")

    @staticmethod
    def make_stored_filename(original_name: str) -> str:
        """Randomized UUID filename with a whitelisted suffix (never the original name)."""
        return f"{uuid.uuid4().hex}{_safe_suffix(original_name)}"

    # -- writes ----------------------------------------------------------------

    def write_original(self, person_id: str, original_name: str, data: bytes) -> Path:
        """Store an untouched copy of the uploaded bytes (FR-011)."""
        target = self.original_dir(person_id) / self.make_stored_filename(original_name)
        return self._write_atomic(target, data)

    def _write_atomic(self, target: Path, data: bytes) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".tmp-{uuid.uuid4().hex}")
        try:
            tmp.write_bytes(data)
            tmp.replace(target)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise StorageError(
                "Failed to write file to private storage",
                details={"path": str(target)},
            ) from exc
        return target

    # -- reads ------------------------------------------------------------------

    def read(self, relative_path: str) -> bytes:
        path = self.resolve_inside(relative_path)
        if not path.is_file():
            raise StorageError("Stored file not found", details={"path": relative_path})
        return path.read_bytes()

    # -- thumbnails -----------------------------------------------------------

    def write_thumbnail(self, person_id: str, photo_id: str, data: bytes) -> Path:
        """Store a generated preview (max ~300px, JPEG) under the person's private
        runtime data — gitignored like every other derived artifact (FR-011)."""
        target = self.thumb_dir(person_id) / f"{photo_id}.jpg"
        return self._write_atomic(target, data)

    def read_thumbnail(self, person_id: str, photo_id: str) -> bytes:
        path = self.resolve_inside("people", person_id, "thumbs", f"{photo_id}.jpg")
        if not path.is_file():
            raise StorageError("Stored thumbnail not found", details={"path": str(path)})
        return path.read_bytes()

    # -- deletion --------------------------------------------------------------

    def delete_person_files(self, person_id: str) -> None:
        """Remove the person's whole directory tree (US5/FR-025)."""
        target = self.person_dir(person_id)
        if target.exists():
            import shutil

            shutil.rmtree(target)

    def delete_photo_files(self, person_id: str, stored_filename: str, photo_id: str) -> None:
        """Remove every copy of one photo (original/normalized/approved + thumbnail)."""
        for directory in ("original", "normalized", "approved"):
            path = self.resolve_inside("people", person_id, directory, stored_filename)
            path.unlink(missing_ok=True)
        thumb = self.resolve_inside("people", person_id, "thumbs", f"{photo_id}.jpg")
        thumb.unlink(missing_ok=True)