"""GET /api/health — liveness + SQLite check (G1, contracts/rest-api.md).

``frigate.reachable`` stays null until Phase 6 wiring; it is deliberately not probed
by this POC phase (constitution IV.3 — unavailable ≠ false).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.config import APP_VERSION

router = APIRouter()


@router.get("/api/health")
def health(session: Session = Depends(get_session)) -> dict:
    database_ok = False
    try:
        session.execute(text("SELECT 1"))
        database_ok = True
    except Exception:
        database_ok = False
    return {
        "status": "ok" if database_ok else "degraded",
        "app_version": APP_VERSION,
        "database": "ok" if database_ok else "error",
        "frigate": {"reachable": None},
    }