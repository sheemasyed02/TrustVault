"""Authenticated directory search for share recipients.

Returns only active users matched by name, email, or exact user id.
Never exposes password hashes or tokens. Empty or tiny queries are rejected
to limit enumeration.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import User

MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 128
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 20

# Escape LIKE metacharacters so user input is matched literally.
_LIKE_ESCAPE_RE = re.compile(r"([\\%_])")


class UserSearchError(Exception):
    def __init__(self, message: str, *, status_code: int, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class UserSearchFilters:
    q: str
    page: int
    page_size: int
    exclude_user_ids: frozenset[uuid.UUID]


@dataclass(frozen=True, slots=True)
class UserSearchResult:
    items: list[User]
    page: int
    page_size: int
    total: int
    total_pages: int


def escape_like_pattern(value: str) -> str:
    return _LIKE_ESCAPE_RE.sub(r"\\\1", value)


def _parse_exclude_ids(raw: str | None) -> frozenset[uuid.UUID]:
    if not raw or not raw.strip():
        return frozenset()
    ids: set[uuid.UUID] = set()
    for part in raw.split(","):
        piece = part.strip()
        if not piece:
            continue
        try:
            ids.add(uuid.UUID(piece))
        except ValueError as exc:
            raise UserSearchError(
                "exclude_user_id must be a valid UUID",
                status_code=422,
                reason_code="INVALID_EXCLUDE_USER_ID",
            ) from exc
    if len(ids) > 20:
        raise UserSearchError(
            "Too many exclude_user_id values",
            status_code=422,
            reason_code="TOO_MANY_EXCLUDES",
        )
    return frozenset(ids)


def validate_search_filters(
    *,
    q: str | None,
    page: int,
    page_size: int,
    exclude_user_id: str | None = None,
) -> UserSearchFilters:
    cleaned = (q or "").strip()
    if len(cleaned) < MIN_QUERY_LENGTH:
        raise UserSearchError(
            f"Search query must be at least {MIN_QUERY_LENGTH} characters",
            status_code=422,
            reason_code="QUERY_TOO_SHORT",
        )
    if len(cleaned) > MAX_QUERY_LENGTH:
        raise UserSearchError(
            "Search query is too long",
            status_code=422,
            reason_code="QUERY_TOO_LONG",
        )
    if page < 1:
        raise UserSearchError(
            "page must be >= 1",
            status_code=422,
            reason_code="INVALID_PAGE",
        )
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise UserSearchError(
            f"page_size must be between 1 and {MAX_PAGE_SIZE}",
            status_code=422,
            reason_code="INVALID_PAGE_SIZE",
        )
    return UserSearchFilters(
        q=cleaned,
        page=page,
        page_size=page_size,
        exclude_user_ids=_parse_exclude_ids(exclude_user_id),
    )


def search_users(
    session: Session,
    *,
    actor: User,
    filters: UserSearchFilters,
) -> UserSearchResult:
    """Search active registered users by name, email, or exact id; exclude caller."""
    excluded = set(filters.exclude_user_ids)
    excluded.add(actor.id)

    try:
        exact_id = uuid.UUID(filters.q)
    except ValueError:
        exact_id = None

    if exact_id is not None:
        match = User.id == exact_id
    else:
        pattern = f"%{escape_like_pattern(filters.q)}%"
        match = or_(
            User.name.ilike(pattern, escape="\\"),
            User.email.ilike(pattern, escape="\\"),
        )

    conditions = [
        User.is_active.is_(True),
        match,
    ]
    if excluded:
        conditions.append(User.id.not_in(list(excluded)))

    total = session.scalar(select(func.count()).select_from(User).where(*conditions))
    assert total is not None

    offset = (filters.page - 1) * filters.page_size
    items = list(
        session.scalars(
            select(User)
            .where(*conditions)
            .order_by(User.name.asc(), User.email.asc(), User.id.asc())
            .offset(offset)
            .limit(filters.page_size)
        ).all()
    )
    total_pages = math.ceil(total / filters.page_size) if total else 0
    return UserSearchResult(
        items=items,
        page=filters.page,
        page_size=filters.page_size,
        total=total,
        total_pages=total_pages,
    )


def user_is_searchable_recipient(user: User, *, actor_id: uuid.UUID) -> bool:
    """Helper for tests: same eligibility rules as search filters."""
    return user.is_active and user.id != actor_id
