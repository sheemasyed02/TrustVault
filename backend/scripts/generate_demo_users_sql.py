"""Generate INSERT SQL for demo users (Argon2id hashes).

Reads DEMO_*_PASSWORD from the environment / backend/.env.
Never prints passwords. Prints SQL to stdout (hashes only).

Usage (from backend directory):

  python scripts\\generate_demo_users_sql.py > scripts\\railway_seed_demo_users.sql
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from app.cli.seed_demo_users import DEMO_ACCOUNTS
from app.core.security import hash_password
from app.services.auth_service import normalize_email


def _require_password(env_name: str) -> str:
    value = (os.getenv(env_name) or "").strip()
    if not value:
        raise SystemExit(f"{env_name} is required")
    if len(value) < 12:
        raise SystemExit(f"{env_name} must be at least 12 characters")
    return value


def main() -> int:
    print("-- TrustVault demo users for Railway / pgAdmin")
    print("-- Generated hashes only. Passwords are never included.")
    print("-- Safe to re-run: skips emails that already exist.")
    print()
    print("BEGIN;")
    print()

    for account in DEMO_ACCOUNTS:
        password = _require_password(account.password_env)
        email = normalize_email(account.email)
        user_id = uuid.uuid4()
        password_hash = hash_password(password)
        # Escape single quotes for SQL literals
        name = account.name.replace("'", "''")
        ph = password_hash.replace("'", "''")

        print(f"-- {email} / {account.role}")
        print(
            "INSERT INTO users (id, name, email, password_hash, role, is_active)\n"
            f"SELECT '{user_id}'::uuid,\n"
            f"       '{name}',\n"
            f"       '{email}',\n"
            f"       '{ph}',\n"
            f"       '{account.role}',\n"
            f"       true\n"
            f"WHERE NOT EXISTS (\n"
            f"  SELECT 1 FROM users WHERE email = '{email}'\n"
            f");"
        )
        print()

    print("COMMIT;")
    print()
    print("-- Verify (no password hashes):")
    print("-- SELECT id, name, email, role, is_active FROM users ORDER BY email;")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
