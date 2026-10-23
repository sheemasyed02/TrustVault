"""Resolve and validate the pytest database URL.

Tests must never silently reuse a production or shared demo database.
Prefer a local PostgreSQL database whose name contains ``test``.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from app.core.database_url import DatabaseURLError, normalize_database_url, redact_database_url

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
REMOTE_BLOCKLIST_SUFFIXES = (
    "neon.tech",
    "rlwy.net",
    "railway.app",
    "amazonaws.com",
    "supabase.co",
)


class TestDatabaseConfigError(RuntimeError):
    """Raised when pytest cannot safely select a database."""

    # Prevent pytest from treating this exception class as a test class.
    __test__ = False


def _parse(url: str):
    raw = (
        url.replace("postgresql+psycopg://", "postgresql://")
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgres://", "postgresql://")
    )
    return urlparse(raw)


def _database_name(url: str) -> str:
    return (_parse(url).path or "").lstrip("/") or ""


def _hostname(url: str) -> str:
    return (_parse(url).hostname or "").lower()


def is_local_database_url(url: str) -> bool:
    return _hostname(url) in LOCAL_HOSTS


def looks_like_test_database_name(name: str) -> bool:
    lowered = (name or "").lower()
    return "test" in lowered


def assert_safe_test_database_url(
    url: str,
    *,
    production_url: str | None = None,
    allow_remote: bool = False,
) -> str:
    """Normalize and refuse URLs that could destroy shared/production data."""
    try:
        normalized = normalize_database_url(url)
    except DatabaseURLError as exc:
        raise TestDatabaseConfigError(str(exc)) from exc

    host = _hostname(normalized)
    db_name = _database_name(normalized)
    redacted = redact_database_url(normalized)

    if not db_name:
        raise TestDatabaseConfigError(
            f"TEST_DATABASE_URL must include a database name ({redacted})."
        )

    if production_url:
        try:
            prod = normalize_database_url(production_url)
        except DatabaseURLError:
            prod = None
        if prod is not None and normalized == prod:
            raise TestDatabaseConfigError(
                "TEST_DATABASE_URL must not be identical to DATABASE_URL."
            )
        if prod is not None and db_name == _database_name(prod) and not looks_like_test_database_name(
            _database_name(prod)
        ):
            raise TestDatabaseConfigError(
                "TEST_DATABASE_URL must not target the production database name."
            )

    local = host in LOCAL_HOSTS
    if not local:
        # Even with the override, refuse obvious shared default names first.
        if db_name.lower() in {"neondb", "railway", "postgres", "defaultdb"}:
            raise TestDatabaseConfigError(
                f"Refusing shared remote database name in {redacted}."
            )
        if not allow_remote:
            raise TestDatabaseConfigError(
                "TEST_DATABASE_URL must point at local PostgreSQL "
                f"(localhost/127.0.0.1). Refusing remote host in {redacted}. "
                "Create a local database named trustvault_test, or set "
                "TRUSTVAULT_ALLOW_REMOTE_TEST_DB=1 only for an isolated "
                "remote database whose name contains 'test'."
            )

    if not looks_like_test_database_name(db_name):
        raise TestDatabaseConfigError(
            "TEST_DATABASE_URL database name must contain 'test' "
            f"(for example trustvault_test); got {redacted}."
        )

    return normalized


def resolve_test_database_url() -> str:
    """Return the normalized URL pytest must use.

    Reads ``TEST_DATABASE_URL`` only. Never falls back to ``DATABASE_URL``.
    """
    raw = (os.environ.get("TEST_DATABASE_URL") or "").strip()
    if not raw:
        raise TestDatabaseConfigError(
            "TEST_DATABASE_URL is required for pytest. "
            "It is not set, so tests will not run against DATABASE_URL. "
            "Create a local database (recommended name: trustvault_test), "
            "set TEST_DATABASE_URL in backend/.env, and apply Alembic migrations."
        )

    production = (os.environ.get("DATABASE_URL") or "").strip() or None
    allow_remote = (os.environ.get("TRUSTVAULT_ALLOW_REMOTE_TEST_DB") or "").strip() in {
        "1",
        "true",
        "True",
        "yes",
        "YES",
    }
    return assert_safe_test_database_url(
        raw,
        production_url=production,
        allow_remote=allow_remote,
    )
