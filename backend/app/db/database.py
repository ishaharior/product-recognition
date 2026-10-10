"""SQLAlchemy engine / session management for the Smart Product Station."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
    # Keep loaded attributes usable after commit: services cache Product rows
    # across short-lived sessions (detached instances must stay readable).
    expire_on_commit=False,
)


def init_db() -> None:
    """Create tables if they do not exist (safe, non-destructive)."""
    from app.db import models  # noqa: F401  (register models)

    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    models.Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
