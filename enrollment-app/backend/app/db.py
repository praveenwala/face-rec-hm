"""SQLAlchemy engine/session setup (SQLite at enrollment-app/data/app.db)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def make_engine(db_path: Path):
    """Create a SQLite engine. check_same_thread=False allows FastAPI's threadpool."""
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )


def make_session_factory(db_path: Path) -> sessionmaker[Session]:
    engine = make_engine(db_path)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)