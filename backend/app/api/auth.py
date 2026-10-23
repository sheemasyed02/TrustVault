"""Authentication HTTP routes."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest, RegisterResponse
from app.services.audit_trail import append_audit_event, append_audit_event_committed
from app.services.auth_service import (
    GENERIC_AUTH_FAILURE,
    AuthFailure,
    AuthSuccess,
    authenticate_user,
    normalize_email,
)
from app.services.register_service import RegisterError, register_viewer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    body: RegisterRequest,
    session: Session = Depends(get_db),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> RegisterResponse:
    """Create a public account. Always assigns platform role VIEWER.

    Client-supplied roles are rejected by schema ``extra=forbid`` (no role field).
    """
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    try:
        user = register_viewer(
            session,
            name=body.name,
            email=str(body.email),
            password=body.password,
        )
    except RegisterError as exc:
        try:
            append_audit_event_committed(
                action="REGISTER",
                outcome="DENIED",
                reason_code=exc.reason_code,
                request_id=request_id,
            )
        except Exception:
            logger.exception("Failed to persist register denial audit")
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    try:
        append_audit_event(
            session,
            action="REGISTER",
            outcome="SUCCESS",
            actor_id=user.id,
            reason_code=None,
            request_id=request_id,
            metadata={"role": "VIEWER"},
        )
    except Exception as exc:
        logger.exception("Registration audit failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account could not be audited",
        ) from exc

    return RegisterResponse(
        id=str(user.id),
        name=user.name,
        email=user.email,
        role=user.role,
        message="Account created as VIEWER. You may request owner access after signing in.",
    )


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

    if isinstance(result, AuthFailure):
        # Actor/reason come from the auth lookup — do not re-query (avoids
        # session visibility edges) and never put password/token in metadata.
        try:
            append_audit_event_committed(
                action="LOGIN",
                outcome="DENIED",
                actor_id=result.actor_id,
                reason_code=result.reason_code,
                request_id=request_id,
                metadata={
                    "email_domain": (
                        normalized.split("@")[-1] if "@" in normalized else None
                    ),
                },
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

    assert isinstance(result, AuthSuccess)
    try:
        append_audit_event(
            session,
            action="LOGIN",
            outcome="SUCCESS",
            actor_id=result.user_id,
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
        access_token=result.access_token,
        token_type="bearer",
        expires_at=result.expires_at,
        expires_in=result.expires_in,
    )
