"""Owner-promotion request workflow for VIEWER accounts."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.db.models import OwnerPromotionRequest, User

logger = logging.getLogger(__name__)


class PromotionError(Exception):
    def __init__(self, message: str, *, status_code: int, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class PromotionListResult:
    items: list[OwnerPromotionRequest]
    page: int
    page_size: int
    total: int
    total_pages: int


def submit_promotion_request(
    session: Session,
    *,
    actor: User,
    justification: str | None,
) -> OwnerPromotionRequest:
    if actor.role != "VIEWER":
        raise PromotionError(
            "Only viewer accounts can request owner access",
            status_code=403,
            reason_code="NOT_VIEWER",
        )
    if not actor.is_active:
        raise PromotionError(
            "Inactive accounts cannot request promotion",
            status_code=403,
            reason_code="INACTIVE",
        )

    pending = session.scalar(
        select(OwnerPromotionRequest).where(
            OwnerPromotionRequest.requester_id == actor.id,
            OwnerPromotionRequest.status == "PENDING",
        )
    )
    if pending is not None:
        raise PromotionError(
            "You already have a pending owner request",
            status_code=409,
            reason_code="PENDING_EXISTS",
        )

    note = (justification or "").strip() or None
    if note is not None and len(note) > 2000:
        raise PromotionError(
            "Justification is too long",
            status_code=422,
            reason_code="JUSTIFICATION_TOO_LONG",
        )

    request = OwnerPromotionRequest(
        id=uuid.uuid4(),
        requester_id=actor.id,
        status="PENDING",
        justification=note,
    )
    session.add(request)
    try:
        session.flush()
    except SQLAlchemyError as exc:
        logger.exception("Failed to persist promotion request")
        raise PromotionError(
            "Unable to submit request",
            status_code=503,
            reason_code="PROMOTION_PERSIST_FAILED",
        ) from exc
    return request


def list_my_promotion_requests(
    session: Session,
    *,
    actor: User,
) -> list[OwnerPromotionRequest]:
    return list(
        session.scalars(
            select(OwnerPromotionRequest)
            .where(OwnerPromotionRequest.requester_id == actor.id)
            .order_by(OwnerPromotionRequest.created_at.desc())
        ).all()
    )


def list_promotion_requests_admin(
    session: Session,
    *,
    status_filter: str | None,
    page: int,
    page_size: int,
) -> PromotionListResult:
    query = select(OwnerPromotionRequest).options(
        joinedload(OwnerPromotionRequest.requester),
    )
    count_query = select(func.count()).select_from(OwnerPromotionRequest)
    if status_filter:
        if status_filter not in {"PENDING", "APPROVED", "REJECTED"}:
            raise PromotionError(
                "Invalid status filter",
                status_code=422,
                reason_code="INVALID_STATUS",
            )
        query = query.where(OwnerPromotionRequest.status == status_filter)
        count_query = count_query.where(OwnerPromotionRequest.status == status_filter)

    total = session.scalar(count_query) or 0
    total_pages = (total + page_size - 1) // page_size if total else 0
    items = list(
        session.scalars(
            query.order_by(
                OwnerPromotionRequest.created_at.desc(),
                OwnerPromotionRequest.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).unique().all()
    )
    return PromotionListResult(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


def review_promotion_request(
    session: Session,
    *,
    admin: User,
    request_id: uuid.UUID,
    decision: str,
    admin_note: str | None,
) -> OwnerPromotionRequest:
    if decision not in {"APPROVED", "REJECTED"}:
        raise PromotionError(
            "Decision must be APPROVED or REJECTED",
            status_code=422,
            reason_code="INVALID_DECISION",
        )

    request = session.scalar(
        select(OwnerPromotionRequest)
        .where(OwnerPromotionRequest.id == request_id)
        .with_for_update()
    )
    if request is None:
        raise PromotionError(
            "Request not found",
            status_code=404,
            reason_code="NOT_FOUND",
        )
    if request.status != "PENDING":
        raise PromotionError(
            "Request has already been reviewed",
            status_code=409,
            reason_code="ALREADY_REVIEWED",
        )

    if request.requester_id == admin.id:
        raise PromotionError(
            "Administrators cannot review their own promotion requests",
            status_code=403,
            reason_code="SELF_REVIEW_FORBIDDEN",
        )

    requester = session.get(User, request.requester_id, with_for_update=True)
    if requester is None:
        raise PromotionError(
            "Requester no longer exists",
            status_code=404,
            reason_code="REQUESTER_MISSING",
        )

    note = (admin_note or "").strip() or None
    if note is not None and len(note) > 2000:
        raise PromotionError(
            "Admin note is too long",
            status_code=422,
            reason_code="NOTE_TOO_LONG",
        )

    now = datetime.now(timezone.utc)
    request.status = decision
    request.admin_note = note
    request.reviewed_by = admin.id
    request.reviewed_at = now

    if decision == "APPROVED":
        # Promote to OWNER without clearing existing document grants.
        if requester.role == "VIEWER":
            requester.role = "OWNER"
        # If already OWNER/ADMIN, approval is a no-op on role but still closes the request.

    try:
        session.flush()
    except SQLAlchemyError as exc:
        logger.exception("Failed to review promotion request")
        raise PromotionError(
            "Unable to review request",
            status_code=503,
            reason_code="REVIEW_PERSIST_FAILED",
        ) from exc

    return request


def update_user_role(
    session: Session,
    *,
    admin: User,
    user_id: uuid.UUID,
    new_role: str,
) -> User:
    """Admin-assigned role change. Never trusts client claims about the admin."""
    if new_role not in {"ADMIN", "OWNER", "VIEWER"}:
        raise PromotionError(
            "Invalid role",
            status_code=422,
            reason_code="INVALID_ROLE",
        )

    target = session.get(User, user_id)
    if target is None:
        raise PromotionError(
            "User not found",
            status_code=404,
            reason_code="NOT_FOUND",
        )

    if target.id == admin.id and new_role != "ADMIN":
        # Count other active admins before demoting self.
        other_admins = (
            session.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.role == "ADMIN",
                    User.is_active.is_(True),
                    User.id != admin.id,
                )
            )
            or 0
        )
        if other_admins < 1:
            raise PromotionError(
                "Cannot demote the last active administrator",
                status_code=400,
                reason_code="LAST_ADMIN",
            )

    if target.role == "ADMIN" and new_role != "ADMIN" and target.is_active:
        admin_count = (
            session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == "ADMIN", User.is_active.is_(True))
            )
            or 0
        )
        if admin_count <= 1:
            raise PromotionError(
                "Cannot demote the last active administrator",
                status_code=400,
                reason_code="LAST_ADMIN",
            )

    previous = target.role
    target.role = new_role
    try:
        session.flush()
    except SQLAlchemyError as exc:
        raise PromotionError(
            "Unable to update role",
            status_code=503,
            reason_code="ROLE_PERSIST_FAILED",
        ) from exc

    logger.info(
        "Admin role update",
        extra={
            "admin_id": str(admin.id),
            "target_id": str(target.id),
            "previous_role": previous,
            "new_role": new_role,
        },
    )
    return target
