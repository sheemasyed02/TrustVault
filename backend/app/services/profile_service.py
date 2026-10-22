"""Authenticated self-service profile and password changes.

Never accepts role, is_active, email, or password hashes from the client.
Never logs passwords or hashes.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.db.models import User

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[\w\s.'-]{2,255}$", re.UNICODE)
MIN_PASSWORD_LEN = 10
MAX_PASSWORD_LEN = 128


class ProfileError(Exception):
    def __init__(self, message: str, *, status_code: int, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.reason_code = reason_code


def update_own_profile(
    session: Session,
    *,
    actor: User,
    name: str,
) -> User:
    """Update the caller's display name only. Email/role/status are immutable here."""
    cleaned = (name or "").strip()
    if not cleaned or not _NAME_RE.match(cleaned):
        raise ProfileError(
            "Enter a valid name (2–255 characters)",
            status_code=422,
            reason_code="INVALID_NAME",
        )

    if cleaned == actor.name:
        return actor

    actor.name = cleaned
    actor.updated_at = datetime.now(timezone.utc)
    try:
        session.flush()
    except SQLAlchemyError as exc:
        logger.exception("Profile name update failed")
        raise ProfileError(
            "Unable to update profile",
            status_code=503,
            reason_code="PROFILE_PERSIST_FAILED",
        ) from exc

    logger.info(
        "Profile name updated",
        extra={"actor_id": str(actor.id), "audit_action": "PROFILE_UPDATE"},
    )
    return actor


def change_own_password(
    session: Session,
    *,
    actor: User,
    current_password: str,
    new_password: str,
    confirm_password: str,
) -> None:
    """Verify current password and replace the hash. Never returns secrets."""
    if not current_password:
        raise ProfileError(
            "Current password is required",
            status_code=422,
            reason_code="CURRENT_PASSWORD_REQUIRED",
        )
    if new_password != confirm_password:
        raise ProfileError(
            "New password and confirmation do not match",
            status_code=422,
            reason_code="PASSWORD_MISMATCH",
        )
    if not new_password or len(new_password) < MIN_PASSWORD_LEN:
        raise ProfileError(
            f"New password must be at least {MIN_PASSWORD_LEN} characters",
            status_code=422,
            reason_code="INVALID_PASSWORD",
        )
    if len(new_password) > MAX_PASSWORD_LEN:
        raise ProfileError(
            f"New password must be at most {MAX_PASSWORD_LEN} characters",
            status_code=422,
            reason_code="INVALID_PASSWORD",
        )
    if new_password == current_password:
        raise ProfileError(
            "New password must be different from the current password",
            status_code=422,
            reason_code="PASSWORD_UNCHANGED",
        )

    if not verify_password(current_password, actor.password_hash):
        # Generic message — do not hint whether the account exists or hash format.
        raise ProfileError(
            "Current password is incorrect",
            status_code=401,
            reason_code="CURRENT_PASSWORD_INVALID",
        )

    actor.password_hash = hash_password(new_password)
    actor.updated_at = datetime.now(timezone.utc)
    try:
        session.flush()
    except SQLAlchemyError as exc:
        logger.exception("Password change persistence failed")
        raise ProfileError(
            "Unable to update password",
            status_code=503,
            reason_code="PASSWORD_PERSIST_FAILED",
        ) from exc

    logger.info(
        "Password changed",
        extra={"actor_id": str(actor.id), "audit_action": "PASSWORD_CHANGE"},
    )
