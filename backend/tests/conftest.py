"""Shared pytest fixtures for database tests.

Uses a connection-level outer transaction plus SAVEPOINT restart so that
endpoint code calling ``session.commit()`` (or ``get_db`` commit behaviour)
cannot leak test users/documents into a shared database.

Database selection: ``TEST_DATABASE_URL`` only (never silent fallback to
``DATABASE_URL`` / Neon production). See ``app.core.test_database``.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.database_url import redact_database_url
from app.core.test_database import TestDatabaseConfigError, resolve_test_database_url
from app.db import session as db_session_module
from app.db.session import reset_engine

# Load backend/.env regardless of the pytest working directory.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_BACKEND_ROOT / ".env")

_TEST_ENGINE: Engine | None = None
_TEST_SESSION_FACTORY: sessionmaker[Session] | None = None
_TEST_DATABASE_URL: str | None = None


def pytest_configure(config: pytest.Config) -> None:
    """Bind the process to TEST_DATABASE_URL before any test imports engines."""
    global _TEST_DATABASE_URL
    try:
        _TEST_DATABASE_URL = resolve_test_database_url()
    except TestDatabaseConfigError as exc:
        # Defer to pytest_sessionstart for a clean abort with the message.
        _TEST_DATABASE_URL = None
        config._trustvault_test_db_error = str(exc)  # type: ignore[attr-defined]
        return

    os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
    get_settings.cache_clear()
    reset_engine()
    config._trustvault_test_db_error = None  # type: ignore[attr-defined]


def pytest_sessionstart(session: pytest.Session) -> None:
    err = getattr(session.config, "_trustvault_test_db_error", None)
    if err:
        pytest.exit(f"Refusing to run tests: {err}", returncode=2)

    url = _TEST_DATABASE_URL or resolve_test_database_url()
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()

    global _TEST_ENGINE, _TEST_SESSION_FACTORY
    _TEST_ENGINE = create_engine(
        url,
        pool_pre_ping=True,
        poolclass=NullPool,
        connect_args={"connect_timeout": 15},
    )
    _TEST_SESSION_FACTORY = sessionmaker(
        bind=_TEST_ENGINE,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    # Point the application session module at the session-scoped test engine
    # so get_db / append_audit_event_committed reuse it (no per-test reconnect).
    db_session_module._engine = _TEST_ENGINE
    db_session_module._SessionLocal = _TEST_SESSION_FACTORY

    # Fixtures historically call reset_engine() when swapping JWT settings.
    # Re-pin to the session-scoped test engine instead of disposing it — that
    # was a major cause of remote reconnect storms and multi-minute suites.
    def _reset_engine_rebind_test() -> None:
        db_session_module._engine = _TEST_ENGINE
        db_session_module._SessionLocal = _TEST_SESSION_FACTORY
        get_settings.cache_clear()

    db_session_module.reset_engine = _reset_engine_rebind_test  # type: ignore[assignment]

    # Fail fast if the schema is missing rather than hanging on the first test.
    try:
        with _TEST_ENGINE.connect() as conn:
            conn.execute(text("SELECT 1"))
            has_users = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'users'"
                )
            ).scalar()
    except Exception as exc:  # noqa: BLE001 — surface connection errors clearly
        pytest.exit(
            "Cannot connect to TEST_DATABASE_URL "
            f"({redact_database_url(url)}): {exc.__class__.__name__}",
            returncode=2,
        )
    if not has_users:
        pytest.exit(
            "TEST_DATABASE_URL is reachable but schema tables are missing. "
            f"Apply migrations against {redact_database_url(url)} with: "
            "alembic upgrade head",
            returncode=2,
        )

    print(
        f"\npytest database: {redact_database_url(url)} "
        f"(from TEST_DATABASE_URL)"
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del session, exitstatus
    global _TEST_ENGINE, _TEST_SESSION_FACTORY
    if _TEST_ENGINE is not None:
        _TEST_ENGINE.dispose()
    _TEST_ENGINE = None
    _TEST_SESSION_FACTORY = None
    db_session_module._engine = None
    db_session_module._SessionLocal = None
    get_settings.cache_clear()


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Provide a transactional session that always rolls back after each test.

    Nested SAVEPOINTs are re-opened after every nested commit/rollback so
    application code that calls ``session.commit()`` only releases the
    SAVEPOINT, not the outer test transaction.
    """
    if _TEST_ENGINE is None or _TEST_SESSION_FACTORY is None:
        pytest.fail("Test database engine was not initialized")

    # Keep the app module pinned to the session-scoped engine even if a test
    # fixture called reset_engine().
    db_session_module._engine = _TEST_ENGINE
    db_session_module._SessionLocal = _TEST_SESSION_FACTORY
    get_settings.cache_clear()

    connection = _TEST_ENGINE.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, expire_on_commit=False)

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess: Session, trans) -> None:  # type: ignore[no-untyped-def]
        nonlocal nested
        if connection.closed:
            return
        if not getattr(trans, "nested", False):
            return
        if not connection.in_transaction():
            return
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
