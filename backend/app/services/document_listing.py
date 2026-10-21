"""Authorized document listing and search.

Access filtering happens in SQL before results are returned. ADMIN role alone
does not expand visibility beyond ownership and active grants.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Document, DocumentPermission, User
from app.services.auth_service import normalize_email

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20
MAX_TITLE_SEARCH_LENGTH = 200
MAX_CATEGORY_LENGTH = 128


class DocumentListValidationError(Exception):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class DocumentListFilters:
    title: str | None = None
    owner_id: uuid.UUID | None = None
    owner_email: str | None = None
    category: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    shared_only: bool = False
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class DocumentListResult:
    items: list[Document]
    total: int
    page: int
    page_size: int
    access_by_document_id: dict[uuid.UUID, str]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def validate_list_filters(
    *,
    title: str | None,
    owner_id: uuid.UUID | None,
    owner_email: str | None,
    category: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
    shared_only: bool = False,
    page: int,
    page_size: int,
) -> DocumentListFilters:
    if page < 1:
        raise DocumentListValidationError(
            "page must be >= 1",
            reason_code="INVALID_PAGE",
        )
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise DocumentListValidationError(
            f"page_size must be between 1 and {MAX_PAGE_SIZE}",
            reason_code="INVALID_PAGE_SIZE",
        )
    clean_title = title.strip() if title else None
    if clean_title == "":
        clean_title = None
    if clean_title and len(clean_title) > MAX_TITLE_SEARCH_LENGTH:
        raise DocumentListValidationError(
            "title search is too long",
            reason_code="TITLE_SEARCH_TOO_LONG",
        )
    clean_category = category.strip() if category else None
    if clean_category == "":
        clean_category = None
    if clean_category and len(clean_category) > MAX_CATEGORY_LENGTH:
        raise DocumentListValidationError(
            "category filter is too long",
            reason_code="CATEGORY_TOO_LONG",
        )
    clean_owner_email = None
    if owner_email and owner_email.strip():
        clean_owner_email = normalize_email(owner_email)
        if len(clean_owner_email) > 320:
            raise DocumentListValidationError(
                "owner_email filter is too long",
                reason_code="OWNER_EMAIL_TOO_LONG",
            )
    if created_from and created_to and created_from > created_to:
        raise DocumentListValidationError(
            "created_from must be <= created_to",
            reason_code="INVALID_DATE_RANGE",
        )
    if owner_id is not None and shared_only:
        raise DocumentListValidationError(
            "shared_only cannot be combined with owner_id",
            reason_code="INVALID_SHARED_ONLY_FILTER",
        )
    return DocumentListFilters(
        title=clean_title,
        owner_id=owner_id,
        owner_email=clean_owner_email,
        category=clean_category,
        created_from=created_from,
        created_to=created_to,
        shared_only=bool(shared_only),
        page=page,
        page_size=page_size,
    )


def accessible_documents_query(user: User) -> Select[tuple[Document]]:
    """Base query: non-deleted docs owned by user or with an active grant."""
    active_grant = exists(
        select(DocumentPermission.id).where(
            DocumentPermission.document_id == Document.id,
            DocumentPermission.user_id == user.id,
            DocumentPermission.revoked_at.is_(None),
            DocumentPermission.permission.in_(("READ", "EDIT")),
        )
    )
    return select(Document).where(
        Document.deleted_at.is_(None),
        or_(Document.owner_id == user.id, active_grant),
    )


def shared_documents_query(user: User) -> Select[tuple[Document]]:
    """Non-deleted docs with an active grant where the caller is not the owner."""
    active_grant = exists(
        select(DocumentPermission.id).where(
            DocumentPermission.document_id == Document.id,
            DocumentPermission.user_id == user.id,
            DocumentPermission.revoked_at.is_(None),
            DocumentPermission.permission.in_(("READ", "EDIT")),
        )
    )
    return select(Document).where(
        Document.deleted_at.is_(None),
        Document.owner_id != user.id,
        active_grant,
    )


def resolve_list_access_levels(
    session: Session,
    *,
    user: User,
    documents: list[Document],
) -> dict[uuid.UUID, str]:
    """Map document id → OWNER | EDIT | READ for the caller (trusted DB state)."""
    levels: dict[uuid.UUID, str] = {}
    need_grants: list[uuid.UUID] = []
    for doc in documents:
        if doc.owner_id == user.id:
            levels[doc.id] = "OWNER"
        else:
            need_grants.append(doc.id)
    if not need_grants:
        return levels

    grants = list(
        session.scalars(
            select(DocumentPermission).where(
                DocumentPermission.document_id.in_(need_grants),
                DocumentPermission.user_id == user.id,
                DocumentPermission.revoked_at.is_(None),
            )
        ).all()
    )
    by_doc = {grant.document_id: grant.permission for grant in grants}
    for doc_id in need_grants:
        permission = by_doc.get(doc_id)
        if permission == "EDIT":
            levels[doc_id] = "EDIT"
        elif permission == "READ":
            levels[doc_id] = "READ"
        # Accessible query already requires a grant; omit ambiguous rows.
    return levels


def list_accessible_documents(
    session: Session,
    *,
    user: User,
    filters: DocumentListFilters,
) -> DocumentListResult:
    query = (
        shared_documents_query(user)
        if filters.shared_only
        else accessible_documents_query(user)
    )

    if filters.title:
        pattern = f"%{_escape_like(filters.title)}%"
        query = query.where(Document.title.ilike(pattern, escape="\\"))
    if filters.owner_id is not None:
        query = query.where(Document.owner_id == filters.owner_id)
    if filters.owner_email is not None:
        query = query.where(
            Document.owner_id.in_(
                select(User.id).where(User.email == filters.owner_email)
            )
        )
    if filters.category:
        query = query.where(Document.category == filters.category)
    if filters.created_from is not None:
        query = query.where(Document.created_at >= filters.created_from)
    if filters.created_to is not None:
        query = query.where(Document.created_at <= filters.created_to)

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = int(session.scalar(count_query) or 0)

    ordered = (
        query.options(joinedload(Document.owner))
        .order_by(Document.created_at.desc(), Document.id.desc())
    )
    offset = (filters.page - 1) * filters.page_size
    items = list(
        session.scalars(ordered.offset(offset).limit(filters.page_size)).unique().all()
    )
    access_by_document_id = resolve_list_access_levels(
        session, user=user, documents=items
    )
    return DocumentListResult(
        items=items,
        total=total,
        page=filters.page,
        page_size=filters.page_size,
        access_by_document_id=access_by_document_id,
    )
