"""Helpers for validating and normalizing DATABASE_URL.

Never log or print the password portion of a database URL.
"""

from __future__ import annotations

from urllib.parse import urlparse


class DatabaseURLError(ValueError):
    """Raised when DATABASE_URL is missing or unsupported."""


def redact_database_url(url: str) -> str:
    """Return a safe summary for logs/errors without credentials."""
    parsed = urlparse(url)
    host = parsed.hostname or "unknown-host"
    port = f":{parsed.port}" if parsed.port else ""
    database = (parsed.path or "").lstrip("/") or "unknown-db"
    return f"{parsed.scheme}://{host}{port}/{database}"


def normalize_database_url(url: str) -> str:
    """Require PostgreSQL and normalize to the sync psycopg driver.

    Accepts common Railway/local forms:
    - postgresql://...
    - postgres://...
    - postgresql+psycopg://...
    - postgresql+asyncpg://... (remapped to sync psycopg for SQLAlchemy/Alembic)

    Rejects SQLite and in-memory URLs.
    """
    cleaned = (url or "").strip()
    if not cleaned:
        raise DatabaseURLError("DATABASE_URL is required")

    lowered = cleaned.lower()
    if lowered.startswith("sqlite:") or ":memory:" in lowered:
        raise DatabaseURLError(
            "SQLite and in-memory databases are not allowed. "
            "Configure a PostgreSQL DATABASE_URL."
        )

    if cleaned.startswith("postgresql+psycopg://"):
        return cleaned
    if cleaned.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + cleaned[len("postgresql+asyncpg://") :]
    if cleaned.startswith("postgresql://"):
        return "postgresql+psycopg://" + cleaned[len("postgresql://") :]
    if cleaned.startswith("postgres://"):
        return "postgresql+psycopg://" + cleaned[len("postgres://") :]

    raise DatabaseURLError(
        "DATABASE_URL must be a PostgreSQL URL "
        f"(received scheme from {redact_database_url(cleaned)})"
    )
