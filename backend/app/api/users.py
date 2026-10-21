"""User profile and directory-search HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.users import UserPublic, UserSearchHit, UserSearchResponse
from app.services.user_search import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    UserSearchError,
    search_users,
    validate_search_filters,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    """Return the authenticated user's safe profile from the database."""
    return current_user


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
