"""User profile and directory-search HTTP routes."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.users import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    ProfileUpdateRequest,
    UserPublic,
    UserSearchHit,
    UserSearchResponse,
)
from app.services.audit_trail import append_audit_event, append_audit_event_committed
from app.services.profile_service import ProfileError, change_own_password, update_own_profile
from app.services.user_search import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    UserSearchError,
    search_users,
    validate_search_filters,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    """Return the authenticated user's safe profile from the database."""
    return current_user


@router.patch("/me", response_model=UserPublic)
def update_current_user_profile(
    body: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> User:
    """Update the caller's display name. Email, role, and status cannot change here."""
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    try:
        updated = update_own_profile(session, actor=current_user, name=body.name)
    except ProfileError as exc:
        try:
            append_audit_event_committed(
                action="PROFILE_UPDATE",
                outcome="DENIED",
                actor_id=current_user.id,
                reason_code=exc.reason_code,
                request_id=request_id,
            )
        except Exception:
            logger.exception("Failed to audit profile update denial")
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    try:
        append_audit_event(
            session,
            action="PROFILE_UPDATE",
            outcome="SUCCESS",
            actor_id=updated.id,
            request_id=request_id,
            metadata={"changed_fields": ["name"]},
        )
    except Exception as exc:
        logger.exception("Audit failed after profile update")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Profile update could not be audited",
        ) from exc

    return updated


@router.post("/me/password", response_model=ChangePasswordResponse)
def change_current_user_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> ChangePasswordResponse:
    """Change the caller's password after verifying the current password.

    JWT access tokens remain cryptographically valid until expiry (no server-side
    revocation store). Clients should clear the in-memory session after success.
    """
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    try:
        change_own_password(
            session,
            actor=current_user,
            current_password=body.current_password,
            new_password=body.new_password,
            confirm_password=body.confirm_password,
        )
    except ProfileError as exc:
        try:
            append_audit_event_committed(
                action="PASSWORD_CHANGE",
                outcome="DENIED",
                actor_id=current_user.id,
                reason_code=exc.reason_code,
                request_id=request_id,
            )
        except Exception:
            logger.exception("Failed to audit password change denial")
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    try:
        append_audit_event(
            session,
            action="PASSWORD_CHANGE",
            outcome="SUCCESS",
            actor_id=current_user.id,
            request_id=request_id,
        )
    except Exception as exc:
        logger.exception("Audit failed after password change")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password change could not be audited",
        ) from exc

    return ChangePasswordResponse(
        message=(
            "Password updated. Sign in again with your new password. "
            "Other devices may keep an existing session until their access token expires."
        )
    )


@router.get("/search", response_model=UserSearchResponse)
def search_registered_users(
    q: str = Query(
        ...,
        description="Name/email substring (min 2 chars), or an exact user UUID",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    exclude_user_id: str | None = Query(
        default=None,
        description="Optional comma-separated user UUIDs to omit (e.g. document owner)",
    ),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> UserSearchResponse:
    """Search active registered users for sharing recipients.

    Authenticated callers only. Excludes the caller, inactive accounts, and any
    `exclude_user_id` values. Matches name/email substrings, or an exact user
    UUID when `q` is a UUID. Returns id, name, and email only.
    """
    try:
        filters = validate_search_filters(
            q=q,
            page=page,
            page_size=page_size,
            exclude_user_id=exclude_user_id,
        )
        result = search_users(session, actor=current_user, filters=filters)
    except UserSearchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    return UserSearchResponse(
        results=[UserSearchHit.model_validate(user) for user in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        total_pages=result.total_pages,
    )
