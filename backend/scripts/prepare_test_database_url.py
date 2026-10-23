"""Derive TEST_DATABASE_URL from DATABASE_URL by swapping the database name.

Writes or updates TEST_DATABASE_URL in backend/.env without printing secrets.
Does not create the database or run migrations.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv

from app.core.database_url import normalize_database_url, redact_database_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND_ROOT / ".env"


def swap_database(url: str, database: str) -> str:
    raw = (
        url.replace("postgresql+psycopg://", "postgresql://")
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgres://", "postgresql://")
    )
    parsed = urlparse(raw)
    return normalize_database_url(urlunparse(parsed._replace(path=f"/{database}")))


def upsert_env_var(path: Path, key: str, value: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(text):
        text = pattern.sub(line, text, count=1)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"\n# Added by scripts/prepare_test_database_url.py\n{line}\n"
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database",
        default="trustvault_test",
        help="Database name to use for TEST_DATABASE_URL",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Also set TRUSTVAULT_ALLOW_REMOTE_TEST_DB=1",
    )
    args = parser.parse_args()

    load_dotenv(ENV_PATH)
    source = (os.environ.get("DATABASE_URL") or "").strip()
    if not source:
        raise SystemExit("DATABASE_URL is not set in backend/.env")

    test_url = swap_database(source, args.database)
    upsert_env_var(ENV_PATH, "TEST_DATABASE_URL", test_url)
    if args.allow_remote:
        upsert_env_var(ENV_PATH, "TRUSTVAULT_ALLOW_REMOTE_TEST_DB", "1")

    print("Updated", ENV_PATH)
    print("TEST_DATABASE_URL ->", redact_database_url(test_url))
    if args.allow_remote:
        print("TRUSTVAULT_ALLOW_REMOTE_TEST_DB=1")
    print("Next: apply migrations with DATABASE_URL pointing at the test DB, then pytest.")


if __name__ == "__main__":
    main()
