"""Idempotent development-only demo user seed.

Never imported or called from application startup.

Required environment variables (passwords are never printed):
  DEMO_ADMIN_PASSWORD
  DEMO_OWNER_PASSWORD
  DEMO_VIEWER_PASSWORD

Run from the backend directory:

  python -m app.cli.seed_demo_users
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import User
from app.db.session import get_session_factory, reset_engine
from app.services.auth_service import normalize_email


@dataclass(frozen=True, slots=True)
class DemoAccount:
    email: str
    role: str
    name: str
    password_env: str


DEMO_ACCOUNTS = (
    DemoAccount(
        email="snovasys@trustvault.demo",
        role="ADMIN",
        name="Snovasys Admin",
        password_env="DEMO_ADMIN_PASSWORD",
    ),
    DemoAccount(
        email="sheema@trustvault.demo",
        role="OWNER",
        name="Sheema Owner",
        password_env="DEMO_OWNER_PASSWORD",
    ),
    DemoAccount(
        email="user@trustvault.demo",
        role="VIEWER",
        name="Demo Viewer",
        password_env="DEMO_VIEWER_PASSWORD",
    ),
)


class SeedConflictError(RuntimeError):
    """Raised when an existing demo account does not match the expected role."""


def _require_demo_password(env_name: str) -> str:
    value = (os.getenv(env_name) or "").strip()
    if not value:
        raise RuntimeError(
            f"{env_name} is required to seed demo users. "
            "Set it in the environment or backend/.env for local development only."
        )
    if len(value) < 12:
        raise RuntimeError(f"{env_name} must be at least 12 characters")
    return value


def seed_demo_users(session) -> dict[str, str]:
    """Create missing demo users. Never resets existing passwords or roles.

    Returns a mapping of email -> created|exists for reporting (no secrets).
    """
    results: dict[str, str] = {}

    for account in DEMO_ACCOUNTS:
        password = _require_demo_password(account.password_env)
        email = normalize_email(account.email)
        existing = session.scalar(select(User).where(User.email == email))

        if existing is None:
            user = User(
                name=account.name,
                email=email,
                password_hash=hash_password(password),
                role=account.role,
                is_active=True,
            )
            session.add(user)
            results[email] = "created"
            continue

        if existing.role != account.role:
            raise SeedConflictError(
                f"Demo account {email} exists with role {existing.role}, "
                f"expected {account.role}. Resolve manually before seeding."
            )
        if not existing.is_active:
            raise SeedConflictError(
                f"Demo account {email} exists but is inactive. "
                "Resolve manually before seeding."
            )

        # Idempotent: leave password_hash and role untouched.
        results[email] = "exists"

    return results


def main() -> int:
    load_dotenv()
    get_settings.cache_clear()
    reset_engine()

    try:
        get_settings()
    except Exception as exc:
        print(f"Configuration error: {exc.__class__.__name__}")
        return 1

    session = get_session_factory()()
    try:
        results = seed_demo_users(session)
        session.commit()
    except SeedConflictError as exc:
        session.rollback()
        print(f"Seed conflict: {exc}")
        return 2
    except RuntimeError as exc:
        session.rollback()
        print(f"Seed aborted: {exc}")
        return 1
    except Exception:
        session.rollback()
        print("Seed failed unexpectedly")
        return 1
    finally:
        session.close()
        reset_engine()
        get_settings.cache_clear()

    print("Demo user seed complete (passwords are not printed):")
    for email, status in results.items():
        print(f"  {email}: {status}")
    print(
        "These accounts are for local/demo use only. "
        "Do not use them as production credentials."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
