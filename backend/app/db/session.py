"""SQLAlchemy engine and session factory."""

from __future__ import annotations

import sys
from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None

# Neon (and similar hosted Postgres) can take well over 10s on a cold path.
# A 15s connect_timeout caused intermittent ConnectionTimeout failures in
# get_current_user, so protected routes returned 500 and the UI showed no data.
_APP_CONNECT_TIMEOUT_SECONDS = 60
_TEST_CONNECT_TIMEOUT_SECONDS = 15


def build_engine_kwargs(*, for_pytest: bool) -> dict[str, Any]:
    """Build SQLAlchemy create_engine kwargs (no secrets; safe to unit-test)."""
    engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if for_pytest:
        # Pytest resets the engine often; NullPool avoids exhausting Postgres
        # max_connections across a large suite. Short connect_timeout fails
        # fast on DNS/network errors instead of multi-minute hangs.
        engine_kwargs["poolclass"] = NullPool
        engine_kwargs["connect_args"] = {
            "connect_timeout": _TEST_CONNECT_TIMEOUT_SECONDS,
        }
    else:
        engine_kwargs["pool_size"] = 5
        engine_kwargs["max_overflow"] = 10
        # Recycle before typical idle proxy drops; keepalives reduce stale sockets.
        engine_kwargs["pool_recycle"] = 280
        engine_kwargs["connect_args"] = {
            "connect_timeout": _APP_CONNECT_TIMEOUT_SECONDS,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        }
    return engine_kwargs


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        engine_kwargs = build_engine_kwargs(for_pytest="pytest" in sys.modules)
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
