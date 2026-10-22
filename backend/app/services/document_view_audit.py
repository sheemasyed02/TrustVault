"""Document view counting and owner/admin view-activity summaries.

Counting rule
-------------
A successful ``DOCUMENT_VIEW`` is recorded when an authenticated, active user
passes ``require_document_read`` and the download route is called with
``disposition=inline`` (in-app preview). Metadata-only GETs and list rows do
**not** count. Attachment downloads use ``DOCUMENT_DOWNLOAD`` and are separate.

To avoid React Strict Mode / remount double-fetches inflating counts, a
successful view from the same actor for the same document within
``VIEW_DEDUPE_SECONDS`` does not create another SUCCESS row (content is still
streamed). Denied attempts are always recorded separately and never increase
the successful view count.

**Owner dashboards** report *external* views only: SUCCESS ``DOCUMENT_VIEW``
events where ``actor_id != document.owner_id``. The owner's own previews remain
in the security audit trail but are excluded from external totals and distinct
external-viewer counts.

Timestamps are always server-generated via the audit trail writer.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Document, User
from app.schemas.audit import (
    DocumentViewActivityItem,
    DocumentViewActivityListResponse,
    DocumentViewPlatformSummary,
)

VIEW_DEDUPE_SECONDS = 45


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def recent_successful_view_exists(
    session: Session,
    *,
    document_id: uuid.UUID,
    actor_id: uuid.UUID,
    within_seconds: int = VIEW_DEDUPE_SECONDS,
) -> bool:
    """True if a SUCCESS DOCUMENT_VIEW was already recorded in the dedupe window."""
    cutoff = _utc_now() - timedelta(seconds=within_seconds)
    existing = session.scalar(
        select(AuditEvent.id)
        .where(
            AuditEvent.document_id == document_id,
            AuditEvent.actor_id == actor_id,
            AuditEvent.action == "DOCUMENT_VIEW",
            AuditEvent.outcome == "SUCCESS",
            AuditEvent.created_at >= cutoff,
        )
        .limit(1)
    )
    return existing is not None


def view_event_metadata(*, actor: User, disposition: str = "inline") -> dict:
    """Safe snapshot fields for authorized audit screens (no secrets)."""
    return {
        "disposition": disposition,
        "actor_role": actor.role,
        "actor_name": actor.name,
        "actor_email": actor.email,
    }


def document_view_stats(
    session: Session,
    *,
    document_id: uuid.UUID,
    exclude_actor_id: uuid.UUID | None = None,
) -> tuple[int, int, datetime | None]:
    """Return (total_views, distinct_viewers, latest_view_at).

    When ``exclude_actor_id`` is set (typically the document owner), that actor's
    SUCCESS views are omitted from the totals (external-view dashboard).
    """
    filters = [
        AuditEvent.document_id == document_id,
        AuditEvent.action == "DOCUMENT_VIEW",
        AuditEvent.outcome == "SUCCESS",
    ]
    if exclude_actor_id is not None:
        filters.append(
            or_(
                AuditEvent.actor_id.is_(None),
                AuditEvent.actor_id != exclude_actor_id,
            )
        )

    total = (
        session.scalar(
            select(func.count()).select_from(AuditEvent).where(*filters)
        )
        or 0
    )
    distinct = (
        session.scalar(
            select(func.count(func.distinct(AuditEvent.actor_id)))
            .select_from(AuditEvent)
            .where(*filters, AuditEvent.actor_id.is_not(None))
        )
        or 0
    )
    latest = session.scalar(
        select(func.max(AuditEvent.created_at)).where(*filters)
    )
    return total, distinct, latest


@dataclass(frozen=True, slots=True)
class _DocViewRow:
    document_id: uuid.UUID
    title: str
    owner_id: uuid.UUID
    owner_name: str
    owner_email: str
    total_views: int
    distinct_viewers: int
    latest_view_at: datetime | None


def list_owner_document_view_activity(
    session: Session,
    *,
    owner: User,
    page: int = 1,
    page_size: int = 20,
) -> DocumentViewActivityListResponse:
    """Per-owned-document view stats for the owner dashboard."""
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 1
    if page_size > 100:
        page_size = 100

    docs_base = select(Document).where(
        Document.owner_id == owner.id,
        Document.deleted_at.is_(None),
    )
    total_docs = session.scalar(
        select(func.count()).select_from(docs_base.subquery())
    ) or 0
    total_pages = math.ceil(total_docs / page_size) if total_docs else 0
    documents = list(
        session.scalars(
            docs_base.order_by(Document.updated_at.desc(), Document.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )

    items: list[DocumentViewActivityItem] = []
    for doc in documents:
        # Owner dashboard: external viewers only (exclude the owner's self-views).
        views, distinct, latest = document_view_stats(
            session,
            document_id=doc.id,
            exclude_actor_id=owner.id,
        )
        items.append(
            DocumentViewActivityItem(
                document_id=doc.id,
                title=doc.title,
                owner_id=owner.id,
                owner_name=owner.name,
                owner_email=owner.email,
                total_views=views,
                distinct_viewers=distinct,
                latest_view_at=latest,
            )
        )

    # External-view summary scoped to this owner's documents.
    owned_ids = select(Document.id).where(
        Document.owner_id == owner.id,
        Document.deleted_at.is_(None),
    )
    owner_total_views = (
        session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.document_id.in_(owned_ids),
                AuditEvent.action == "DOCUMENT_VIEW",
                AuditEvent.outcome == "SUCCESS",
                or_(
                    AuditEvent.actor_id.is_(None),
                    AuditEvent.actor_id != owner.id,
                ),
            )
        )
        or 0
    )

    return DocumentViewActivityListResponse(
        results=items,
        page=page,
        page_size=page_size,
        total=total_docs,
        total_pages=total_pages,
        summary=DocumentViewPlatformSummary(
            total_view_events=owner_total_views,
            documents_with_views=sum(1 for i in items if i.total_views > 0),
            most_viewed=sorted(items, key=lambda i: i.total_views, reverse=True)[:5],
        ),
    )


def list_admin_document_view_activity(
    session: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    owner_id: uuid.UUID | None = None,
    viewer_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> DocumentViewActivityListResponse:
    """Platform-wide per-document view stats for administrators."""
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 1
    if page_size > 100:
        page_size = 100

    # Documents that have at least one SUCCESS view matching filters, or all docs
    # when searching by title/owner without requiring views.
    view_filter = (
        select(AuditEvent.document_id)
        .where(
            AuditEvent.action == "DOCUMENT_VIEW",
            AuditEvent.outcome == "SUCCESS",
            AuditEvent.document_id.is_not(None),
        )
        .distinct()
    )
    if viewer_id is not None:
        view_filter = view_filter.where(AuditEvent.actor_id == viewer_id)
    if created_from is not None:
        view_filter = view_filter.where(AuditEvent.created_at >= created_from)
    if created_to is not None:
        view_filter = view_filter.where(AuditEvent.created_at <= created_to)

    docs_stmt = (
        select(Document, User)
        .join(User, User.id == Document.owner_id)
        .where(Document.deleted_at.is_(None))
    )
    q_norm = (q or "").strip()
    if q_norm:
        pattern = f"%{q_norm}%"
        docs_stmt = docs_stmt.where(
            or_(
                Document.title.ilike(pattern),
                User.name.ilike(pattern),
                User.email.ilike(pattern),
            )
        )
    if owner_id is not None:
        docs_stmt = docs_stmt.where(Document.owner_id == owner_id)
    if viewer_id is not None or created_from is not None or created_to is not None:
        docs_stmt = docs_stmt.where(Document.id.in_(view_filter))

    total_docs = session.scalar(
        select(func.count()).select_from(docs_stmt.subquery())
    ) or 0
    total_pages = math.ceil(total_docs / page_size) if total_docs else 0

    rows = list(
        session.execute(
            docs_stmt.order_by(Document.updated_at.desc(), Document.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )

    items: list[DocumentViewActivityItem] = []
    for doc, owner in rows:
        # When date/viewer filters apply, count only matching views.
        view_where = [
            AuditEvent.document_id == doc.id,
            AuditEvent.action == "DOCUMENT_VIEW",
            AuditEvent.outcome == "SUCCESS",
        ]
        if viewer_id is not None:
            view_where.append(AuditEvent.actor_id == viewer_id)
        if created_from is not None:
            view_where.append(AuditEvent.created_at >= created_from)
        if created_to is not None:
            view_where.append(AuditEvent.created_at <= created_to)

        total = session.scalar(
            select(func.count()).select_from(AuditEvent).where(*view_where)
        ) or 0
        distinct = (
            session.scalar(
                select(func.count(func.distinct(AuditEvent.actor_id)))
                .select_from(AuditEvent)
                .where(*view_where, AuditEvent.actor_id.is_not(None))
            )
            or 0
        )
        latest = session.scalar(
            select(func.max(AuditEvent.created_at)).where(*view_where)
        )
        items.append(
            DocumentViewActivityItem(
                document_id=doc.id,
                title=doc.title,
                owner_id=owner.id,
                owner_name=owner.name,
                owner_email=owner.email,
                total_views=total,
                distinct_viewers=distinct,
                latest_view_at=latest,
            )
        )

    platform_total = (
        session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action == "DOCUMENT_VIEW",
                AuditEvent.outcome == "SUCCESS",
            )
        )
        or 0
    )
    docs_with_views = (
        session.scalar(
            select(func.count(func.distinct(AuditEvent.document_id))).where(
                AuditEvent.action == "DOCUMENT_VIEW",
                AuditEvent.outcome == "SUCCESS",
                AuditEvent.document_id.is_not(None),
            )
        )
        or 0
    )

    # Most-viewed across the platform (top 5), independent of current page.
    most_rows = list(
        session.execute(
            select(
                AuditEvent.document_id,
                func.count().label("cnt"),
            )
            .where(
                AuditEvent.action == "DOCUMENT_VIEW",
                AuditEvent.outcome == "SUCCESS",
                AuditEvent.document_id.is_not(None),
            )
            .group_by(AuditEvent.document_id)
            .order_by(func.count().desc())
            .limit(5)
        ).all()
    )
    most_viewed: list[DocumentViewActivityItem] = []
    for doc_id, cnt in most_rows:
        doc = session.get(Document, doc_id)
        if doc is None:
            continue
        owner = session.get(User, doc.owner_id)
        if owner is None:
            continue
        _, distinct, latest = document_view_stats(session, document_id=doc.id)
        most_viewed.append(
            DocumentViewActivityItem(
                document_id=doc.id,
                title=doc.title,
                owner_id=owner.id,
                owner_name=owner.name,
                owner_email=owner.email,
                total_views=int(cnt),
                distinct_viewers=distinct,
                latest_view_at=latest,
            )
        )

    return DocumentViewActivityListResponse(
        results=items,
        page=page,
        page_size=page_size,
        total=total_docs,
        total_pages=total_pages,
        summary=DocumentViewPlatformSummary(
            total_view_events=platform_total,
            documents_with_views=docs_with_views,
            most_viewed=most_viewed,
        ),
    )
