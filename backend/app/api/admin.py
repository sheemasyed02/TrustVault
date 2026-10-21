"""Administrator-only user management and audit inspection APIs.

ADMIN may list users, change account active status, list audit events, and
verify the audit hash chain. ADMIN role alone never grants document content
read/download permission.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.models import AuditEvent, User
from app.db.session import get_db
from app.schemas.admin_users import (
    AdminSummaryResponse,
    AdminUserListResponse,
    AdminUserStatusUpdateRequest,
    AdminUserSummary,
)
from app.schemas.audit import (
    AuditEventListResponse,
    AuditEventResponse,
    AuditIntegrityResponse,
)
from app.services.audit_trail import (
    append_audit_event,
    list_audit_events,
    verify_audit_chain,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _event_response(event: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse(
        id=event.id,
        created_at=event.created_at,
        actor_id=event.actor_id,
        action=event.action,
        document_id=event.document_id,
        target_user_id=event.target_user_id,
        outcome=event.outcome,
        reason_code=event.reason_code,
        request_id=event.request_id,
        metadata=dict(event.metadata_json or {}),
        previous_hash=event.previous_hash,
        event_hash=event.event_hash,
    )


@router.get("/summary", response_model=AdminSummaryResponse)
def admin_summary(
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> AdminSummaryResponse:
    """Accurate user and audit outcome counts for the admin dashboard."""
    del current_user
    users_total = session.scalar(select(func.count()).select_from(User)) or 0
    users_active = (
        session.scalar(
            select(func.count()).select_from(User).where(User.is_active.is_(True))
        )
        or 0
    )
    users_inactive = users_total - users_active
    audit_success_total = (
        session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.outcome == "SUCCESS")
        )
        or 0
    )
    audit_denied_total = (
        session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.outcome == "DENIED")
        )
        or 0
    )
    return AdminSummaryResponse(
        users_total=users_total,
        users_active=users_active,
        users_inactive=users_inactive,
        audit_success_total=audit_success_total,
        audit_denied_total=audit_denied_total,
    )


@router.get("/users", response_model=AdminUserListResponse)
def list_users_admin(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> AdminUserListResponse:
    """List registered accounts. ADMIN only. Does not return password hashes."""
    del current_user  # authorization already enforced
    total = session.scalar(select(func.count()).select_from(User)) or 0
    total_pages = math.ceil(total / page_size) if total else 0
    users = list(
        session.scalars(
            select(User)
            .order_by(User.created_at.desc(), User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return AdminUserListResponse(
        results=[AdminUserSummary.model_validate(u) for u in users],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


def _active_admin_count(session: Session) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "ADMIN", User.is_active.is_(True))
        )
        or 0
    )


@router.patch("/users/{user_id}", response_model=AdminUserSummary)
def update_user_status(
    body: AdminUserStatusUpdateRequest,
    user_id: uuid.UUID = Path(...),
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_db),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> AdminUserSummary:
    """Activate or deactivate a user account. ADMIN only. Fail-closed on audit.

    Policy: admins cannot deactivate themselves. Deactivating an ADMIN is
    rejected when that account is the last active administrator.
    Role changes are not accepted (schema ``extra=forbid``; only ``is_active``).
    """
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if target.is_active and body.is_active is False:
        if target.role == "ADMIN" and _active_admin_count(session) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last active administrator",
            )
        if target.id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Administrators cannot deactivate their own account",
            )

    previous = target.is_active
    if previous == body.is_active:
        append_audit_event(
            session,
            action="ADMIN_USER_STATUS_UPDATE",
            outcome="SUCCESS",
            actor_id=current_user.id,
            target_user_id=target.id,
            reason_code="NO_CHANGES",
            request_id=request_id,
            metadata={"is_active": body.is_active},
        )
        return AdminUserSummary.model_validate(target)

    target.is_active = body.is_active
    session.flush()
    try:
        append_audit_event(
            session,
            action="ADMIN_USER_STATUS_UPDATE",
            outcome="SUCCESS",
            actor_id=current_user.id,
            target_user_id=target.id,
            reason_code="ACTIVATED" if body.is_active else "DEACTIVATED",
            request_id=request_id,
            metadata={"previous_is_active": previous, "is_active": body.is_active},
        )
    except Exception as exc:
        logger.exception("Audit failed after user status update")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User status update could not be audited",
        ) from exc

    return AdminUserSummary.model_validate(target)


@router.get("/audit/events", response_model=AuditEventListResponse)
def list_audit_events_admin(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    document_id: uuid.UUID | None = Query(default=None),
    outcome: str | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> AuditEventListResponse:
    """Paginated audit events with filters. ADMIN only. No document bytes."""
    del current_user
    if outcome is not None and outcome not in {"SUCCESS", "DENIED"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="outcome must be SUCCESS or DENIED",
        )
    result = list_audit_events(
        session,
        page=page,
        page_size=page_size,
        actor_id=actor_id,
        action=action,
        document_id=document_id,
        outcome=outcome,
        created_from=created_from,
        created_to=created_to,
    )
    return AuditEventListResponse(
        results=[_event_response(e) for e in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        total_pages=result.total_pages,
    )


@router.get("/audit/integrity", response_model=AuditIntegrityResponse)
def verify_audit_integrity(
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> AuditIntegrityResponse:
    """Recalculate the audit hash chain. ADMIN only."""
    del current_user
    result = verify_audit_chain(session)
    return AuditIntegrityResponse(
        valid=result.valid,
        event_count=result.event_count,
        checked_count=result.checked_count,
        first_failure_index=result.first_failure_index,
        first_failure_event_id=result.first_failure_event_id,
        reason_code=result.reason_code,
        detail=result.detail,
    )
