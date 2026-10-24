"""Password-reset token generation, hashing, validation, and single-use consume.

Raw tokens are never persisted. Only SHA-256 digests are stored. Passwords and
raw tokens must never appear in logs or API responses.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import PasswordResetToken, User

logger = logging.getLogger(__name__)

# At least 32 bytes of cryptographically secure entropy.
_TOKEN_ENTROPY_BYTES = 32


class PasswordResetTokenError(Exception):
    """Internal failure for password-reset token operations."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class IssuedResetToken:
    """Raw token returned once at issuance — never re-read from storage."""

    raw_token: str
    record: PasswordResetToken


def generate_raw_reset_token(*, nbytes: int = _TOKEN_ENTROPY_BYTES) -> str:
    """Return a URL-safe token with at least ``nbytes`` of random entropy."""
    if nbytes < _TOKEN_ENTROPY_BYTES:
        raise ValueError("Reset tokens require at least 32 bytes of entropy")
    return secrets.token_urlsafe(nbytes)


def hash_reset_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest used for persistence and lookup."""
    if not raw_token:
        raise ValueError("Reset token is required")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_password_reset_token(
    session: Session,
    *,
    user: User,
    settings: Settings,
) -> IssuedResetToken:
    """Persist a hashed single-use token for ``user`` and return the raw value once."""
    if not user.is_active:
        raise PasswordResetTokenError(
            "Account is not eligible for password reset",
            reason_code="INACTIVE_ACCOUNT",
        )

    expire_minutes = settings.password_reset_token_expire_minutes
    if expire_minutes <= 0:
        raise PasswordResetTokenError(
            "PASSWORD_RESET_TOKEN_EXPIRE_MINUTES must be a positive integer",
            reason_code="INVALID_EXPIRY_CONFIG",
        )

    raw_token = generate_raw_reset_token()
    token_hash = hash_reset_token(raw_token)
    now = _utc_now()
    record = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(minutes=expire_minutes),
        used_at=None,
        created_at=now,
    )
    session.add(record)
    try:
        session.flush()
    except SQLAlchemyError as exc:
        logger.exception(
            "Password reset token persistence failed",
            extra={"user_id": str(user.id)},
        )
        raise PasswordResetTokenError(
            "Unable to create password reset token",
            reason_code="TOKEN_PERSIST_FAILED",
        ) from exc

    logger.info(
        "Password reset token issued",
        extra={
            "user_id": str(user.id),
            "token_id": str(record.id),
            "expires_at": record.expires_at.isoformat(),
        },
    )
    return IssuedResetToken(raw_token=raw_token, record=record)


def get_valid_password_reset_token(
    session: Session,
    *,
    raw_token: str,
    now: datetime | None = None,
) -> PasswordResetToken | None:
    """Return the unused, unexpired token row for ``raw_token``, else None."""
    if not raw_token or not raw_token.strip():
        return None

    token_hash = hash_reset_token(raw_token.strip())
    record = session.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    if record is None:
        return None

    current = now or _utc_now()
    if record.used_at is not None:
        return None

    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= current:
        return None

    return record


def consume_password_reset_token(
    session: Session,
    *,
    record: PasswordResetToken,
    now: datetime | None = None,
) -> PasswordResetToken:
    """Mark ``record`` as used. Raises if already consumed or expired."""
    current = now or _utc_now()

    if record.used_at is not None:
        raise PasswordResetTokenError(
            "Password reset token has already been used",
            reason_code="TOKEN_ALREADY_USED",
        )

    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= current:
        raise PasswordResetTokenError(
            "Password reset token has expired",
            reason_code="TOKEN_EXPIRED",
        )

    record.used_at = current
    try:
        session.flush()
    except SQLAlchemyError as exc:
        logger.exception(
            "Password reset token consume failed",
            extra={"token_id": str(record.id), "user_id": str(record.user_id)},
        )
        raise PasswordResetTokenError(
            "Unable to consume password reset token",
            reason_code="TOKEN_CONSUME_FAILED",
        ) from exc

    logger.info(
        "Password reset token consumed",
        extra={"token_id": str(record.id), "user_id": str(record.user_id)},
    )
    return record
