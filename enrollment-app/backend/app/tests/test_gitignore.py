"""Privacy — data path gitignored (spec SC-007, constitution II.4)."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]  # repo root (above enrollment-app/)


def _check_ignore(rel_path: str) -> bool:
    proc = subprocess.run(
        ["git", "check-ignore", "-q", rel_path],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    return proc.returncode == 0


def test_app_db_is_ignored():
    assert _check_ignore("enrollment-app/data/app.db")


def test_photo_bytes_path_is_ignored():
    assert _check_ignore("enrollment-app/data/people/abc-123/original/x.jpg")
    assert _check_ignore("enrollment-app/data/people/abc-123/normalized/x.png")


def test_default_data_dir_lives_under_enrollment_app():
    from app.config import DEFAULT_DATA_DIR

    assert DEFAULT_DATA_DIR.name == "data"
    assert DEFAULT_DATA_DIR.parent.name == "enrollment-app"


def test_venv_and_node_modules_ignored():
    assert _check_ignore("enrollment-app/backend/.venv/bin/python")
    assert _check_ignore("enrollment-app/frontend/node_modules/react/index.js")
    assert _check_ignore("enrollment-app/frontend/dist/index.html")