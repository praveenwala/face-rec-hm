"""Shared fixtures. Every test uses an isolated temp data dir — the real
enrollment-app/data/ is never touched by tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def app(tmp_path):
    return create_app(data_dir=tmp_path / "data")


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def settings(app):
    return app.state.settings