"""User profile HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.db.models import User
from app.schemas.users import UserPublic

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    """Return the authenticated user's safe profile from the database."""
    return current_user
