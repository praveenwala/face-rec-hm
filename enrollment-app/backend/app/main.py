"""FastAPI application factory (Feature 002, Phase 1 — Foundation).

The server binds to 127.0.0.1 only (run.sh / uvicorn CLI). The app itself holds no
network binding — loopback-only is enforced by the startup command and asserted by
tests (spec FR-002, SC-011).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.future import router as future_router
from app.api.health import router as health_router
from app.api.people import router as people_router
from app.api.photos import router as photos_router
from app.api.system import router as system_router
from app.config import APP_VERSION, Settings, load_settings
from app.db import make_session_factory

# Import models so SQLAlchemy registers all tables before create_all.
from app import models  # noqa: F401


def create_app(data_dir: Path | None = None) -> FastAPI:
    settings: Settings = load_settings(data_dir)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.people_root.mkdir(parents=True, exist_ok=True)

    session_factory = make_session_factory(settings.db_path)

    app = FastAPI(
        title="Known Person Enrollment Manager",
        version=APP_VERSION,
        description=(
            "Local management surface for the known-person library (Feature 002). "
            "Localhost-only; enrollment into Frigate is not enabled in this phase."
        ),
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.storage = None  # instantiated by service deps as needed (Phase 2+)

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(system_router)
    app.include_router(people_router)
    app.include_router(photos_router)
    app.include_router(future_router)
    return app


# Module-level instance for `uvicorn app.main:app`.
app = create_app()