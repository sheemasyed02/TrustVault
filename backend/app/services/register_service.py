"""Public account registration — always creates VIEWER accounts."""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import User
from app.services.auth_service import normalize_email

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[\w\s.'-]{2,255}$", re.UNICODE)


class RegisterError(Exception):
    def __init__(self, message: str, *, status_code: int, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.reason_code = reason_code


def register_viewer(
    session: Session,
    *,
    name: str,
    email: str,
    password: str,
) -> User:
    """Create an active VIEWER account. Client-supplied roles are never accepted."""
    cleaned_name = (name or "").strip()
    if not cleaned_name or not _NAME_RE.match(cleaned_name):
        raise RegisterError(
            "Enter a valid name (2–255 characters)",
            status_code=422,
            reason_code="INVALID_NAME",
        )
    if not password or len(password) < 10 or len(password) > 128:
        raise RegisterError(
            "Password must be between 10 and 128 characters",
            status_code=422,
            reason_code="INVALID_PASSWORD",
        )

    normalized = normalize_email(email)
    existing = session.scalar(select(User).where(User.email == normalized))
    if existing is not None:
        # Generic message — do not confirm which emails are registered.
        raise RegisterError(
            "Unable to create account with the provided details",
            status_code=409,
            reason_code="EMAIL_UNAVAILABLE",
        )

    user = User(
        id=uuid.uuid4(),
        name=cleaned_name,
        email=normalized,
        password_hash=hash_password(password),
        role="VIEWER",
        is_active=True,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:
        raise RegisterError(
            "Unable to create account with the provided details",
            status_code=409,
            reason_code="EMAIL_UNAVAILABLE",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("Registration persistence failed")
        raise RegisterError(
            "Unable to create account",
            status_code=503,
            reason_code="REGISTER_PERSIST_FAILED",
        ) from exc

    return user
