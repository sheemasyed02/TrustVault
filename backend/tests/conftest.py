"""Shared pytest fixtures for database tests."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database_url import DatabaseURLError
from app.db.session import get_session_factory, reset_engine

# Load backend/.env regardless of the pytest working directory.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Provide a transactional session rolled back after each test."""
    get_settings.cache_clear()
    reset_engine()
    try:
        get_settings()
    except (DatabaseURLError, Exception) as exc:
        pytest.skip(f"DATABASE_URL is not usable: {exc.__class__.__name__}")

    session = get_session_factory()()
    session.begin()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        reset_engine()
        get_settings.cache_clear()
