"""Verify DATABASE_URL can connect and run SELECT 1.

Loads backend/.env via application Settings (same path as FastAPI / Alembic).
Never prints passwords or full connection strings.

Usage (from backend/):

  python scripts/check_database_connection.py

Exit codes:
  0 — connected and SELECT 1 succeeded
  1 — configuration or connection failure
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.database_url import DatabaseURLError, redact_database_url  # noqa: E402
from app.db.session import check_database_connection, reset_engine  # noqa: E402


def main() -> int:
    get_settings.cache_clear()
    reset_engine()
    try:
        settings = get_settings()
    except (DatabaseURLError, Exception) as exc:
        print("Configuration error:", type(exc).__name__)
        # Avoid dumping ValidationError bodies that might include env snippets.
        detail = str(exc)
        if "DATABASE_URL" in detail or isinstance(exc, DatabaseURLError):
            print("Set DATABASE_URL in backend/.env (see backend/.env.example).")
        return 1

    print("Checking:", redact_database_url(settings.database_url))
    try:
        check_database_connection()
    except Exception as exc:
        print("Connection failed:", type(exc).__name__)
        return 1

    print("OK: SELECT 1 succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
