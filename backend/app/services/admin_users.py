"""Administrator user listing and profile assembly (no secrets, no file bytes)."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Document, DocumentPermission, OwnerPromotionRequest, User
from app.schemas.admin_users import (
    AdminPromotionSummary,
    AdminUserActivitySummary,
    AdminUserListResponse,
    AdminUserProfileResponse,
    AdminUserSummary,
)


@dataclass(frozen=True, slots=True)
class AdminUserListFilters:
    q: str | None = None
    role: str | None = None
    is_active: bool | None = None
    promotion_status: str | None = None


def _normalize_q(q: str | None) -> str | None:
    if q is None:
        return None
    trimmed = q.strip()
    return trimmed or None


def _latest_promotion_by_user(
    session: Session,
    user_ids: list[uuid.UUID],
) -> dict[uuid.UUID, OwnerPromotionRequest]:
    """Map requester_id → most recent promotion request (any status)."""
    if not user_ids:
        return {}
    rows = list(
        session.scalars(
            select(OwnerPromotionRequest)
            .where(OwnerPromotionRequest.requester_id.in_(user_ids))
            .order_by(
                OwnerPromotionRequest.created_at.desc(),
                OwnerPromotionRequest.id.desc(),
            )
        ).all()
    )
    latest: dict[uuid.UUID, OwnerPromotionRequest] = {}
    for row in rows:
        if row.requester_id not in latest:
            latest[row.requester_id] = row
    return latest


def _pending_promotion_by_user(
    session: Session,
    user_ids: list[uuid.UUID],
) -> dict[uuid.UUID, OwnerPromotionRequest]:
    if not user_ids:
        return {}
    rows = list(
        session.scalars(
            select(OwnerPromotionRequest).where(
                OwnerPromotionRequest.requester_id.in_(user_ids),
                OwnerPromotionRequest.status == "PENDING",
            )
        ).all()
    )
    return {row.requester_id: row for row in rows}


def _promotion_summary(req: OwnerPromotionRequest | None) -> AdminPromotionSummary | None:
    if req is None:
        return None
    return AdminPromotionSummary(
        id=req.id,
        status=req.status,
        justification=req.justification,
        admin_note=req.admin_note,
        created_at=req.created_at,
        reviewed_at=req.reviewed_at,
        reviewed_by=req.reviewed_by,
    )


def _to_summary(
    user: User,
    *,
    promotion: OwnerPromotionRequest | None,
) -> AdminUserSummary:
    return AdminUserSummary(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        account_status="Active" if user.is_active else "Inactive",
        promotion_request_status=promotion.status if promotion else None,
        promotion_requested_at=promotion.created_at if promotion else None,
        pending_promotion_id=promotion.id if promotion and promotion.status == "PENDING" else None,
    )


def summarize_admin_user(session: Session, user: User) -> AdminUserSummary:
    """Build a list-row summary including latest/pending promotion badge."""
    pending = session.scalar(
        select(OwnerPromotionRequest).where(
            OwnerPromotionRequest.requester_id == user.id,
            OwnerPromotionRequest.status == "PENDING",
        )
    )
    latest = None
    if pending is None:
        latest = session.scalar(
            select(OwnerPromotionRequest)
            .where(OwnerPromotionRequest.requester_id == user.id)
            .order_by(
                OwnerPromotionRequest.created_at.desc(),
                OwnerPromotionRequest.id.desc(),
            )
            .limit(1)
        )
    return _to_summary(user, promotion=pending or latest)


def list_admin_users(
    session: Session,
    *,
    page: int = 1,
    page_size: int = 50,
    filters: AdminUserListFilters | None = None,
) -> AdminUserListResponse:
    filters = filters or AdminUserListFilters()
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 1
    if page_size > 100:
        page_size = 100

    stmt = select(User)
    q = _normalize_q(filters.q)
    if q is not None:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(User.name.ilike(pattern), User.email.ilike(pattern))
        )
    if filters.role is not None:
        stmt = stmt.where(User.role == filters.role.upper())
    if filters.is_active is not None:
        stmt = stmt.where(User.is_active.is_(filters.is_active))

    promo_status = (filters.promotion_status or "").strip().upper() or None
    if promo_status == "NONE":
        pending_ids = select(OwnerPromotionRequest.requester_id).where(
            OwnerPromotionRequest.status == "PENDING"
        )
        stmt = stmt.where(User.id.not_in(pending_ids))
    elif promo_status in {"PENDING", "APPROVED", "REJECTED"}:
        # Match users whose *latest* request has this status via EXISTS on latest row.
        latest = (
            select(
                OwnerPromotionRequest.requester_id.label("rid"),
                func.max(OwnerPromotionRequest.created_at).label("max_created"),
            )
            .group_by(OwnerPromotionRequest.requester_id)
            .subquery()
        )
        matching = (
            select(OwnerPromotionRequest.requester_id)
            .join(
                latest,
                (OwnerPromotionRequest.requester_id == latest.c.rid)
                & (OwnerPromotionRequest.created_at == latest.c.max_created),
            )
            .where(OwnerPromotionRequest.status == promo_status)
        )
        stmt = stmt.where(User.id.in_(matching))

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    total_pages = math.ceil(total / page_size) if total else 0
    users = list(
        session.scalars(
            stmt.order_by(User.created_at.desc(), User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    user_ids = [u.id for u in users]
    # Prefer pending for list badge; otherwise show latest request status.
    pending = _pending_promotion_by_user(session, user_ids)
    latest = _latest_promotion_by_user(session, user_ids)
    results = [
        _to_summary(
            user,
            promotion=pending.get(user.id) or latest.get(user.id),
        )
        for user in users
    ]
    return AdminUserListResponse(
        results=results,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


def get_admin_user_profile(
    session: Session,
    *,
    user_id: uuid.UUID,
) -> AdminUserProfileResponse | None:
    user = session.get(User, user_id)
    if user is None:
        return None

    pending = session.scalar(
        select(OwnerPromotionRequest).where(
            OwnerPromotionRequest.requester_id == user.id,
            OwnerPromotionRequest.status == "PENDING",
        )
    )
    latest = session.scalar(
        select(OwnerPromotionRequest)
        .where(OwnerPromotionRequest.requester_id == user.id)
        .order_by(
            OwnerPromotionRequest.created_at.desc(),
            OwnerPromotionRequest.id.desc(),
        )
        .limit(1)
    )
    promotion = pending or latest

    owned_total = (
        session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.owner_id == user.id, Document.deleted_at.is_(None))
        )
        or 0
    )
    grants_received = (
        session.scalar(
            select(func.count())
            .select_from(DocumentPermission)
            .where(
                DocumentPermission.user_id == user.id,
                DocumentPermission.revoked_at.is_(None),
            )
        )
        or 0
    )
    audit_as_actor = (
        session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.actor_id == user.id)
        )
        or 0
    )
    audit_denied = (
        session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.actor_id == user.id, AuditEvent.outcome == "DENIED")
        )
        or 0
    )

    summary = _to_summary(user, promotion=promotion)
    return AdminUserProfileResponse(
        **summary.model_dump(),
        latest_promotion=_promotion_summary(promotion),
        activity=AdminUserActivitySummary(
            owned_documents=owned_total,
            active_grants_received=grants_received,
            audit_events_as_actor=audit_as_actor,
            denied_audit_events_as_actor=audit_denied,
        ),
    )
