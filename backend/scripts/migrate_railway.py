"""Apply Alembic migrations using RAILWAY_DATABASE_URL.

Does not print passwords. Intended for a reachable Railway Postgres URL
(usually DATABASE_PUBLIC_URL from the Railway dashboard when run from a laptop).

Usage (from backend/):
    python scripts/migrate_railway.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database_url import (  # noqa: E402
    DatabaseURLError,
    normalize_database_url,
    redact_database_url,
)


def main() -> int:
    load_dotenv(ROOT / ".env")
    raw = os.getenv("RAILWAY_DATABASE_URL", "").strip()
    if not raw:
        print(
            "RAILWAY_DATABASE_URL is missing from backend/.env. "
            "Set it to Railway's public Postgres URL when running from your laptop."
        )
        return 1

    try:
        url = normalize_database_url(raw)
    except DatabaseURLError as exc:
        print(f"Invalid RAILWAY_DATABASE_URL: {exc}")
        return 1

    print("Migrating:", redact_database_url(url))

    try:
        engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 15},
        )
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        host_hint = redact_database_url(url)
        print("Could not connect to Railway Postgres at", host_hint)
        print("error_type:", type(exc).__name__)
        if "railway.internal" in host_hint:
            print(
                "This hostname only works inside Railway's private network. "
                "From your laptop, put Railway's DATABASE_PUBLIC_URL into "
                "RAILWAY_DATABASE_URL in backend/.env, then rerun this script."
            )
        return 1

    # Point Alembic at Railway for this process only; do not rewrite local DATABASE_URL.
    os.environ["DATABASE_URL"] = url
    from app.core.config import get_settings
    from app.db.session import reset_engine

    get_settings.cache_clear()
    reset_engine()

    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, "head")

    with engine.connect() as connection:
        tables = [
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN
                          ('users', 'documents', 'document_permissions',
                           'audit_events', 'alembic_version')
                    ORDER BY table_name
                    """
                )
            )
        ]
        version = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()

    print("tables:", tables)
    print("alembic_version:", version)
    print("Railway migration complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
