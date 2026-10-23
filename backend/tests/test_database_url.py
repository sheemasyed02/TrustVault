"""Unit tests for DATABASE_URL validation (no live database connection)."""

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


def test_normalize_preserves_neon_ssl_query_params():
    """Neon direct URLs keep sslmode/channel_binding after scheme rewrite."""
    raw = (
        "postgresql://user:secret@ep-example.us-east-2.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    normalized = normalize_database_url(raw)
    assert normalized.startswith("postgresql+psycopg://")
    assert "sslmode=require" in normalized
    assert "channel_binding=require" in normalized
    assert "secret" in normalized  # still present in URL object for the driver
    assert "secret" not in redact_database_url(normalized)


def test_normalize_preserves_pooler_host_and_query():
    raw = (
        "postgresql://user:secret@ep-example-pooler.us-east-2.aws.neon.tech/neondb"
        "?sslmode=require"
    )
    normalized = normalize_database_url(raw)
    assert "-pooler." in normalized
    assert normalized.endswith("?sslmode=require") or "?sslmode=require" in normalized


def test_reject_empty_database_url():
    with pytest.raises(DatabaseURLError, match="required"):
        normalize_database_url("   ")


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
