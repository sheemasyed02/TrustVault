"""Administrator-only user management and audit inspection APIs.

ADMIN may list users, change account active status, list audit events, and
verify the audit hash chain. ADMIN role alone never grants document content
read/download permission.
"""

from __future__ import annotations

import logging
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
    AdminUserProfileResponse,
    AdminUserRoleUpdateRequest,
    AdminUserStatusUpdateRequest,
    AdminUserSummary,
)
from app.schemas.audit import (
    AuditEventListResponse,
    AuditIntegrityResponse,
    DocumentViewActivityListResponse,
)
from app.services.admin_users import (
    AdminUserListFilters,
    get_admin_user_profile,
    list_admin_users,
    summarize_admin_user,
)
from app.services.audit_trail import (
    append_audit_event,
    enrich_audit_event_responses,
    list_audit_events,
    verify_audit_chain,
)
from app.services.document_view_audit import list_admin_document_view_activity
from app.services.promotion_service import PromotionError, update_user_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


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
    q: str | None = Query(
        default=None,
        max_length=200,
        description="Search by name or email (case-insensitive)",
    ),
    role: str | None = Query(
        default=None,
        description="Filter by ADMIN, OWNER, or VIEWER",
    ),
    is_active: bool | None = Query(
        default=None,
        description="Filter by account activation status",
    ),
    promotion_status: str | None = Query(
        default=None,
        description="PENDING, APPROVED, REJECTED, or NONE (no pending / no match)",
    ),
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> AdminUserListResponse:
    """List registered accounts with search/filters. ADMIN only. No password hashes."""
    del current_user  # authorization already enforced
    if role is not None and role.upper() not in {"ADMIN", "OWNER", "VIEWER"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="role must be ADMIN, OWNER, or VIEWER",
        )
    if promotion_status is not None and promotion_status.upper() not in {
        "PENDING",
        "APPROVED",
        "REJECTED",
        "NONE",
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="promotion_status must be PENDING, APPROVED, REJECTED, or NONE",
        )
    return list_admin_users(
        session,
        page=page,
        page_size=page_size,
        filters=AdminUserListFilters(
            q=q,
            role=role,
            is_active=is_active,
            promotion_status=promotion_status,
        ),
    )


@router.get("/users/{user_id}", response_model=AdminUserProfileResponse)
def get_user_profile_admin(
    user_id: uuid.UUID = Path(...),
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> AdminUserProfileResponse:
    """Inspect one registered account. ADMIN only. Never returns secrets or file bytes."""
    del current_user
    profile = get_admin_user_profile(session, user_id=user_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return profile


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
        return summarize_admin_user(session, target)

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

    return summarize_admin_user(session, target)


@router.patch("/users/{user_id}/role", response_model=AdminUserSummary)
def update_user_role_admin(
    body: AdminUserRoleUpdateRequest,
    user_id: uuid.UUID = Path(...),
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_db),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> AdminUserSummary:
    """Assign OWNER or VIEWER only. Never assigns ADMIN. ADMIN-only, audited."""
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    previous_role = None
    target = session.get(User, user_id)
    if target is not None:
        previous_role = target.role
    try:
        updated = update_user_role(
            session,
            admin=current_user,
            user_id=user_id,
            new_role=body.role,
        )
    except PromotionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    try:
        append_audit_event(
            session,
            action="ADMIN_USER_ROLE_UPDATE",
            outcome="SUCCESS",
            actor_id=current_user.id,
            target_user_id=updated.id,
            reason_code="ROLE_CHANGED" if previous_role != updated.role else "NO_CHANGES",
            request_id=request_id,
            metadata={"previous_role": previous_role, "role": updated.role},
        )
    except Exception as exc:
        logger.exception("Audit failed after role update")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Role update could not be audited",
        ) from exc

    return summarize_admin_user(session, updated)


@router.get("/audit/document-views", response_model=DocumentViewActivityListResponse)
def list_document_view_activity_admin(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(
        default=None,
        max_length=200,
        description="Search document title, owner name, or owner email",
    ),
    owner_id: uuid.UUID | None = Query(default=None),
    viewer_id: uuid.UUID | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> DocumentViewActivityListResponse:
    """Platform-wide document view counts. ADMIN only — never returns file bytes."""
    del current_user
    return list_admin_document_view_activity(
        session,
        page=page,
        page_size=page_size,
        q=q,
        owner_id=owner_id,
        viewer_id=viewer_id,
        created_from=created_from,
        created_to=created_to,
    )


@router.get("/audit/events", response_model=AuditEventListResponse)
def list_audit_events_admin(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    document_id: uuid.UUID | None = Query(default=None),
    owner_id: uuid.UUID | None = Query(
        default=None,
        description="Filter events for documents owned by this user",
    ),
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
        owner_id=owner_id,
        outcome=outcome,
        created_from=created_from,
        created_to=created_to,
    )
    return AuditEventListResponse(
        results=enrich_audit_event_responses(session, result.items),
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
