"""SQLAlchemy engine and session factory."""

from __future__ import annotations

import sys
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        # Pytest resets the engine often; NullPool avoids exhausting Postgres
        # max_connections across a large suite.
        engine_kwargs: dict = {"pool_pre_ping": True}
        if "pytest" in sys.modules:
            engine_kwargs["poolclass"] = NullPool
        else:
            engine_kwargs["pool_size"] = 5
            engine_kwargs["max_overflow"] = 10
        _engine = create_engine(settings.database_url, **engine_kwargs)
        _SessionLocal = sessionmaker(
            bind=_engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped session.

    Successful handlers must persist work: without an explicit commit, SQLAlchemy
    rolls back the transaction when the session closes, so flushed inserts
    (uploads, grants, metadata edits) would disappear after a 2xx response.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Dispose cached engine (used by tests)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def check_database_connection() -> bool:
    """Return True when a simple SELECT 1 succeeds."""
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
