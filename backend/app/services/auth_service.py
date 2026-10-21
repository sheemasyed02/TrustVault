"""Authentication use cases against PostgreSQL users."""

from __future__ import annotations

import logging
import uuid
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


def authenticate_user(
    session: Session,
    *,
    email: str,
    password: str,
    settings: Settings,
) -> tuple[str, datetime, int] | None:
    """Return token details on success, or None for any authentication failure.

    Uses one generic failure path for unknown email, bad password, and inactive
    accounts so responses do not reveal which case occurred.
    """
    normalized = normalize_email(email)
    user = session.scalar(select(User).where(User.email == normalized))

    if user is None or not user.is_active:
        logger.info(
            "Authentication failed",
            extra={"auth_event": "login_failed"},
        )
        return None

    if not verify_password(password, user.password_hash):
        logger.info(
            "Authentication failed",
            extra={"auth_event": "login_failed"},
        )
        return None

    token, expires_at = create_access_token(
        subject_user_id=user.id,
        settings=settings,
    )
    expires_in = settings.access_token_expire_minutes * 60
    logger.info(
        "Authentication succeeded",
        extra={"auth_event": "login_succeeded"},
    )
    return token, expires_at, expires_in


def get_user_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)
