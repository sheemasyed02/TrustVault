"""Authentication HTTP routes."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, LoginResponse
from app.services.audit_trail import append_audit_event, append_audit_event_committed
from app.services.auth_service import (
    GENERIC_AUTH_FAILURE,
    authenticate_user,
    normalize_email,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> LoginResponse:
    """Exchange email/password for a signed access token.

    Failures return a generic 401. Password hashes are never returned.
    Stateless JWT logout is not implemented here; issued tokens remain valid
    until expiry unless a revocation mechanism is added later.
    """
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    normalized = normalize_email(str(body.email))

    try:
        result = authenticate_user(
            session,
            email=normalized,
            password=body.password,
            settings=settings,
        )
    except ValueError:
        # Misconfigured JWT secret — do not leak configuration details.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication is not configured",
        ) from None

    if result is None:
        user = session.scalar(select(User).where(User.email == normalized))
        reason = (
            "INACTIVE_ACCOUNT"
            if user is not None and not user.is_active
            else "INVALID_CREDENTIALS"
        )
        try:
            append_audit_event_committed(
                action="LOGIN",
                outcome="DENIED",
                actor_id=user.id if user is not None else None,
                reason_code=reason,
                request_id=request_id,
                metadata={"email_domain": normalized.split("@")[-1] if "@" in normalized else None},
            )
        except Exception:
            logger.exception(
                "Failed to persist login denial audit",
                extra={"audit_persisted": False},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_AUTH_FAILURE,
        )

    access_token, expires_at, expires_in = result
    user = session.scalar(select(User).where(User.email == normalized))
    if user is None:
        # Should not happen after successful authenticate_user.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_AUTH_FAILURE,
        )

    try:
        append_audit_event(
            session,
            action="LOGIN",
            outcome="SUCCESS",
            actor_id=user.id,
            reason_code=None,
            request_id=request_id,
        )
    except Exception as exc:
        logger.exception("Login succeeded but audit write failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login could not be audited",
        ) from exc

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_at=expires_at,
        expires_in=expires_in,
    )
