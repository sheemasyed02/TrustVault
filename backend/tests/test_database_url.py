"""Unit tests for DATABASE_URL validation."""

import pytest

from app.core.database_url import DatabaseURLError, normalize_database_url, redact_database_url


def test_normalize_postgresql_url():
    assert (
        normalize_database_url("postgresql://user:secret@localhost:5432/trustvault_db")
        == "postgresql+psycopg://user:secret@localhost:5432/trustvault_db"
    )


def test_normalize_asyncpg_url_to_psycopg():
    assert (
        normalize_database_url(
            "postgresql+asyncpg://user:secret@localhost:5432/trustvault_db"
        )
        == "postgresql+psycopg://user:secret@localhost:5432/trustvault_db"
    )


def test_reject_sqlite_fallback():
    with pytest.raises(DatabaseURLError, match="SQLite"):
        normalize_database_url("sqlite:///./local.db")


def test_reject_memory_database():
    with pytest.raises(DatabaseURLError, match="SQLite|in-memory"):
        normalize_database_url("sqlite+pysqlite:///:memory:")


def test_redact_hides_password():
    redacted = redact_database_url(
        "postgresql+psycopg://user:super-secret@localhost:5432/trustvault_db"
    )
    assert "super-secret" not in redacted
    assert "localhost" in redacted
    assert "trustvault_db" in redacted
