"""Shared fixtures. Every test uses an isolated temp data dir — the real
enrollment-app/data/ is never touched by tests.

The face-detection model (Phase 4) is copied into each temp data dir from the real
app runtime cache when present, so quality analysis behaves identically to
production. Detection-dependent tests skip cleanly when the model has not been
fetched (run ``scripts/fetch_models.sh``).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_DATA_DIR
from app.main import create_app

REAL_MODEL_PATH = DEFAULT_DATA_DIR / "models" / "facedet.onnx"
MODEL_AVAILABLE = REAL_MODEL_PATH.exists()


@pytest.fixture()
def app(tmp_path):
    return create_app(data_dir=tmp_path / "data")


@pytest.fixture(autouse=True)
def _provision_model(app):
    """Copy the fetched model into the isolated data dir so analysis runs for real."""
    if not MODEL_AVAILABLE:
        return
    dst = app.state.settings.models_dir / "facedet.onnx"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REAL_MODEL_PATH, dst)


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def settings(app):
    return app.state.settings