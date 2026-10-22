"""Shared pytest fixtures for database tests.

Uses a connection-level outer transaction plus SAVEPOINT restart so that
endpoint code calling ``session.commit()`` (or ``get_db`` commit behaviour)
cannot leak test users/documents into the developer's real database.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database_url import DatabaseURLError
from app.db.session import get_engine, reset_engine

# Load backend/.env regardless of the pytest working directory.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Provide a transactional session that always rolls back after each test.

    Nested SAVEPOINTs are re-opened after every nested commit/rollback so
    application code that calls ``session.commit()`` only releases the
    SAVEPOINT, not the outer test transaction.
    """
    get_settings.cache_clear()
    reset_engine()
    try:
        get_settings()
    except (DatabaseURLError, Exception) as exc:
        pytest.skip(f"DATABASE_URL is not usable: {exc.__class__.__name__}")

    engine = get_engine()
    connection = engine.connect()
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
        reset_engine()
        get_settings.cache_clear()
