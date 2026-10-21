"""Authentication HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.auth import LoginRequest, LoginResponse
from app.services.auth_service import GENERIC_AUTH_FAILURE, authenticate_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    """Exchange email/password for a signed access token.

    Failures return a generic 401. Password hashes are never returned.
    Stateless JWT logout is not implemented here; issued tokens remain valid
    until expiry unless a revocation mechanism is added later.
    """
    try:
        result = authenticate_user(
            session,
            email=str(body.email),
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_AUTH_FAILURE,
        )

    access_token, expires_at, expires_in = result
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_at=expires_at,
        expires_in=expires_in,
    )
