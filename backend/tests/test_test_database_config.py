"""Unit tests for pytest database URL safety checks (no live DB)."""

import pytest

from app.core.test_database import (
    TestDatabaseConfigError,
    assert_safe_test_database_url,
    resolve_test_database_url,
)


def test_accepts_local_trustvault_test():
    url = assert_safe_test_database_url(
        "postgresql+psycopg://u:p@localhost:5432/trustvault_test",
        production_url="postgresql+psycopg://u:p@localhost:5432/trustvault_db",
    )
    assert "trustvault_test" in url


def test_rejects_missing_test_in_name():
    with pytest.raises(TestDatabaseConfigError, match="contain 'test'"):
        assert_safe_test_database_url(
            "postgresql+psycopg://u:p@localhost:5432/trustvault_db"
        )


def test_rejects_identical_production_url():
    shared = "postgresql+psycopg://u:p@localhost:5432/trustvault_test"
    with pytest.raises(TestDatabaseConfigError, match="identical"):
        assert_safe_test_database_url(shared, production_url=shared)


def test_rejects_remote_without_override():
    with pytest.raises(TestDatabaseConfigError, match="local PostgreSQL"):
        assert_safe_test_database_url(
            "postgresql://u:p@ep-x.us-east-2.aws.neon.tech/trustvault_test"
            "?sslmode=require",
            allow_remote=False,
        )


def test_allows_remote_isolated_test_db_with_override():
    url = assert_safe_test_database_url(
        "postgresql://u:p@ep-x.us-east-2.aws.neon.tech/trustvault_test"
        "?sslmode=require",
        production_url=(
            "postgresql://u:p@ep-x.us-east-2.aws.neon.tech/neondb?sslmode=require"
        ),
        allow_remote=True,
    )
    assert "trustvault_test" in url


def test_rejects_remote_neondb_even_with_override():
    with pytest.raises(TestDatabaseConfigError, match="shared remote"):
        assert_safe_test_database_url(
            "postgresql://u:p@ep-x.us-east-2.aws.neon.tech/neondb?sslmode=require",
            allow_remote=True,
        )


def test_resolve_requires_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    with pytest.raises(TestDatabaseConfigError, match="TEST_DATABASE_URL is required"):
        resolve_test_database_url()
