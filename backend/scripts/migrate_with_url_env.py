"""Apply Alembic migrations using a chosen env var for DATABASE_URL.

Examples:
  python scripts/migrate_with_url_env.py DATABASE_URL
  python scripts/migrate_with_url_env.py RAILWAY_DATABASE_URL

Never prints passwords. Refuses clearly unreachable Railway internal hosts
when run from outside Railway.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/migrate_with_url_env.py ENV_VAR_NAME")
        return 2

    env_name = sys.argv[1]
    raw = (os.getenv(env_name) or "").strip()
    if not raw:
        print(f"{env_name} is missing or empty in the environment / backend/.env")
        return 1

    parsed = urlparse(raw)
    host = parsed.hostname or ""
    print(f"Using {env_name} -> host={host} db={(parsed.path or '').lstrip('/')}")

    if host.endswith(".railway.internal"):
        print(
            "This host only works inside Railway's private network.\n"
            "From your laptop, set RAILWAY_DATABASE_URL to the Postgres "
            "DATABASE_PUBLIC_URL (proxy host like *.proxy.rlwy.net), then retry.\n"
            "Do not paste the password into chat."
        )
        return 1

    from app.core.config import get_settings
    from app.core.database_url import normalize_database_url, redact_database_url
    from alembic import command
    from alembic.config import Config

    normalized = normalize_database_url(raw)
    print("Normalized target:", redact_database_url(normalized))

    # Force Alembic/settings to use this URL for this process only.
    os.environ["DATABASE_URL"] = normalized
    get_settings.cache_clear()

    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    print("Migration complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
