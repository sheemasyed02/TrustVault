"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import AccessTokenError, decode_access_token
from app.db.models import User
from app.db.session import get_db
from app.services.auth_service import get_user_by_id

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Validate bearer token and return the current active database user.

    Roles and active status are always loaded from PostgreSQL, never trusted
    from client-supplied JSON or unverified token claims.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials, settings=settings)
        user_id = uuid.UUID(payload["sub"])
    except (AccessTokenError, ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = get_user_by_id(session, user_id)
    if user is not None and not user.is_active:
        # Best-effort denial audit. Never block or wait on the chain lock —
        # another request may still hold pg_advisory_xact_lock in tests or
        # under load; the 401 must still be returned.
        try:
            from app.services.audit_trail import try_append_audit_event_committed

            try_append_audit_event_committed(
                action="AUTH_INACTIVE_ACCESS",
                outcome="DENIED",
                actor_id=user.id,
                reason_code="INACTIVE_ACCOUNT",
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require an active ADMIN role from PostgreSQL (never from client claims)."""
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    return current_user
