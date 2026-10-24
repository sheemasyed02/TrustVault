"""Forgot-password and reset-password use cases.

Never discloses whether an email is registered. Never logs passwords, raw
tokens, or complete reset URLs. JWT access tokens are not revoked server-side
(stateless design) — same limitation as authenticated password change.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password
from app.db.models import PasswordResetToken, User
from app.services.auth_service import normalize_email
from app.services.brevo_email import (
    EmailConfigurationError,
    EmailDeliveryError,
    send_password_reset_email,
)
from app.services.password_reset_rate_limit import (
    PasswordResetRateLimitExceeded,
    check_forgot_password_rate_limit,
)
from app.services.password_reset_tokens import (
    PasswordResetTokenError,
    create_password_reset_token,
    hash_reset_token,
)
from app.services.profile_service import MAX_PASSWORD_LEN, MIN_PASSWORD_LEN

logger = logging.getLogger(__name__)

GENERIC_FORGOT_PASSWORD_MESSAGE = (
    "If an eligible account exists for that email, a password reset link will be sent."
)

GENERIC_RESET_TOKEN_FAILURE = (
    "This password reset link is invalid or has expired. Request a new one."
)

GENERIC_EMAIL_FAILURE = (
    "Unable to process the password reset request right now. Please try again later."
)


class PasswordResetError(Exception):
    def __init__(self, message: str, *, status_code: int, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.reason_code = reason_code


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def find_eligible_reset_user(session: Session, *, email: str) -> User | None:
    """Return an active user for self-service reset, else None.

    No ADMIN exclusion policy is implemented in this codebase (admins already
    use authenticated ``POST /users/me/password``). Inactive accounts are
    ineligible and must be indistinguishable from unknown emails publicly.
    """
    normalized = normalize_email(email)
    user = session.scalar(select(User).where(User.email == normalized))
    if user is None or not user.is_active:
        return None
    return user


def request_password_reset(
    session: Session,
    *,
    email: str,
    client_ip: str,
    settings: Settings,
) -> str:
    """Start forgot-password. Always returns the same public message on success.

    Raises ``PasswordResetError`` for rate limits and email-provider failures
    without revealing whether the account exists.
    """
    normalized = normalize_email(str(email))
    try:
        check_forgot_password_rate_limit(
            client_ip=client_ip,
            email=normalized,
            settings=settings,
        )
    except PasswordResetRateLimitExceeded as exc:
        logger.info(
            "Forgot-password rate limited",
            extra={"auth_event": "forgot_password_rate_limited"},
        )
        raise PasswordResetError(
            exc.message,
            status_code=429,
            reason_code=exc.reason_code,
        ) from exc

    user = find_eligible_reset_user(session, email=normalized)
    if user is None:
        logger.info(
            "Forgot-password completed without mail",
            extra={"auth_event": "forgot_password_no_eligible_user"},
        )
        return GENERIC_FORGOT_PASSWORD_MESSAGE

    try:
        issued = create_password_reset_token(session, user=user, settings=settings)
    except PasswordResetTokenError as exc:
        logger.exception(
            "Forgot-password token creation failed",
            extra={"auth_event": "forgot_password_token_failed"},
        )
        raise PasswordResetError(
            GENERIC_EMAIL_FAILURE,
            status_code=503,
            reason_code=exc.reason_code,
        ) from exc

    try:
        send_password_reset_email(
            settings,
            to_email=user.email,
            to_name=user.name,
            raw_token=issued.raw_token,
        )
    except EmailConfigurationError as exc:
        logger.error(
            "Forgot-password email not configured",
            extra={
                "auth_event": "forgot_password_email_config",
                "missing_count": len(exc.missing),
            },
        )
        raise PasswordResetError(
            GENERIC_EMAIL_FAILURE,
            status_code=503,
            reason_code="EMAIL_NOT_CONFIGURED",
        ) from exc
    except EmailDeliveryError as exc:
        logger.error(
            "Forgot-password Brevo delivery failed",
            extra={
                "auth_event": "forgot_password_email_failed",
                "reason_code": exc.reason_code,
                "http_status": exc.status_code,
            },
        )
        raise PasswordResetError(
            GENERIC_EMAIL_FAILURE,
            status_code=503,
            reason_code=exc.reason_code,
        ) from exc

    logger.info(
        "Forgot-password email accepted by provider",
        extra={
            "auth_event": "forgot_password_email_accepted",
            "user_id": str(user.id),
            "token_id": str(issued.record.id),
        },
    )
    return GENERIC_FORGOT_PASSWORD_MESSAGE


def _validate_new_password(*, new_password: str, confirm_password: str) -> None:
    if new_password != confirm_password:
        raise PasswordResetError(
            "New password and confirmation do not match",
            status_code=422,
            reason_code="PASSWORD_MISMATCH",
        )
    if not new_password or len(new_password) < MIN_PASSWORD_LEN:
        raise PasswordResetError(
            f"New password must be at least {MIN_PASSWORD_LEN} characters",
            status_code=422,
            reason_code="INVALID_PASSWORD",
        )
    if len(new_password) > MAX_PASSWORD_LEN:
        raise PasswordResetError(
            f"New password must be at most {MAX_PASSWORD_LEN} characters",
            status_code=422,
            reason_code="INVALID_PASSWORD",
        )


def reset_password_with_token(
    session: Session,
    *,
    raw_token: str,
    new_password: str,
    confirm_password: str,
) -> User:
    """Validate token, atomically consume it, and set a new password hash."""
    _validate_new_password(
        new_password=new_password,
        confirm_password=confirm_password,
    )

    token_value = (raw_token or "").strip()
    if not token_value or len(token_value) > 512:
        raise PasswordResetError(
            GENERIC_RESET_TOKEN_FAILURE,
            status_code=400,
            reason_code="INVALID_TOKEN",
        )

    try:
        token_hash = hash_reset_token(token_value)
    except ValueError as exc:
        raise PasswordResetError(
            GENERIC_RESET_TOKEN_FAILURE,
            status_code=400,
            reason_code="INVALID_TOKEN",
        ) from exc

    now = _utc_now()
    # Lock the token row so concurrent resets cannot both succeed.
    record = session.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == token_hash)
        .with_for_update()
    )
    if record is None:
        raise PasswordResetError(
            GENERIC_RESET_TOKEN_FAILURE,
            status_code=400,
            reason_code="INVALID_TOKEN",
        )

    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if record.used_at is not None or expires_at <= now:
        raise PasswordResetError(
            GENERIC_RESET_TOKEN_FAILURE,
            status_code=400,
            reason_code=(
                "TOKEN_ALREADY_USED" if record.used_at is not None else "TOKEN_EXPIRED"
            ),
        )

    # Conditional update: only one concurrent request can consume the token.
    consume_result = session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.id == record.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .values(used_at=now)
    )
    if consume_result.rowcount != 1:
        raise PasswordResetError(
            GENERIC_RESET_TOKEN_FAILURE,
            status_code=400,
            reason_code="TOKEN_CONSUME_RACE",
        )

    user = session.get(User, record.user_id, with_for_update=True)
    if user is None or not user.is_active:
        raise PasswordResetError(
            GENERIC_RESET_TOKEN_FAILURE,
            status_code=400,
            reason_code="USER_INELIGIBLE",
        )

    user.password_hash = hash_password(new_password)
    user.updated_at = now

    # Invalidate any other outstanding reset tokens for this account.
    session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.id != record.id,
        )
        .values(used_at=now)
    )

    try:
        session.flush()
    except SQLAlchemyError as exc:
        logger.exception(
            "Password reset persistence failed",
            extra={"user_id": str(user.id), "token_id": str(record.id)},
        )
        raise PasswordResetError(
            "Unable to update password",
            status_code=503,
            reason_code="PASSWORD_PERSIST_FAILED",
        ) from exc

    logger.info(
        "Password reset completed",
        extra={
            "auth_event": "password_reset_succeeded",
            "user_id": str(user.id),
            "token_id": str(record.id),
        },
    )
    return user
