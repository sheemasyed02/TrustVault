"""Authentication use cases against PostgreSQL users."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import create_access_token, verify_password
from app.db.models import User

logger = logging.getLogger(__name__)

GENERIC_AUTH_FAILURE = "Invalid email or password"


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True, slots=True)
class AuthSuccess:
    access_token: str
    expires_at: datetime
    expires_in: int
    user_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class AuthFailure:
    """Internal failure details for audit only — never expose to HTTP clients."""

    reason_code: str
    actor_id: uuid.UUID | None


def authenticate_user(
    session: Session,
    *,
    email: str,
    password: str,
    settings: Settings,
) -> AuthSuccess | AuthFailure:
    """Authenticate and return success or structured failure for auditing.

    HTTP responses must still use ``GENERIC_AUTH_FAILURE`` for every failure
    branch so clients cannot distinguish unknown email, bad password, or
    inactive accounts. Passwords are never logged or returned.
    """
    normalized = normalize_email(email)
    user = session.scalar(select(User).where(User.email == normalized))

    if user is None:
        logger.info(
            "Authentication failed",
            extra={"auth_event": "login_failed"},
        )
        return AuthFailure(reason_code="INVALID_CREDENTIALS", actor_id=None)

    if not user.is_active:
        logger.info(
            "Authentication failed",
            extra={"auth_event": "login_failed"},
        )
        return AuthFailure(reason_code="INACTIVE_ACCOUNT", actor_id=user.id)

    if not verify_password(password, user.password_hash):
        logger.info(
            "Authentication failed",
            extra={"auth_event": "login_failed"},
        )
        return AuthFailure(reason_code="INVALID_CREDENTIALS", actor_id=user.id)

    token, expires_at = create_access_token(
        subject_user_id=user.id,
        settings=settings,
    )
    expires_in = settings.access_token_expire_minutes * 60
    logger.info(
        "Authentication succeeded",
        extra={"auth_event": "login_succeeded"},
    )
    return AuthSuccess(
        access_token=token,
        expires_at=expires_at,
        expires_in=expires_in,
        user_id=user.id,
    )


def get_user_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)
