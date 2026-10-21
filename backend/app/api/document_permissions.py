"""Owner-only document permission list, grant, and revoke routes."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.documents import get_document_audit
from app.db.models import User
from app.db.session import get_db
from app.schemas.documents import (
    PermissionGrantRequest,
    PermissionGrantResponse,
    PermissionListResponse,
    PermissionRevokeResponse,
    PermissionUserSummary,
)
from app.services.document_authorization import DocumentAuthorizationError
from app.services.document_sharing import (
    DocumentSharingError,
    audit_sharing_event,
    grant_document_permission,
    list_document_permissions,
    revoke_document_permission,
)
from app.services.upload_audit import UploadAuditHook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["document-permissions"])


def _user_summary(user: User) -> PermissionUserSummary:
    return PermissionUserSummary.model_validate(user)


def _grant_response(grant, *, regranted: bool = False) -> PermissionGrantResponse:
    return PermissionGrantResponse(
        id=grant.id,
        document_id=grant.document_id,
        user=_user_summary(grant.user),
        permission=grant.permission,
        granted_at=grant.created_at,
        granted_by=_user_summary(grant.grantor),
        regranted=regranted,
    )


def _safe_audit(
    audit: UploadAuditHook,
    *,
    action: str,
    outcome: str,
    reason_code: str | None,
    actor_id: uuid.UUID | None,
    document_id: uuid.UUID | None,
    target_user_id: uuid.UUID | None,
    request_id: str | None,
) -> None:
    """Best-effort denial audit; never hide the original denial if audit fails."""
    try:
        audit_sharing_event(
            audit,
            action=action,
            outcome=outcome,
            reason_code=reason_code,
            actor_id=actor_id,
            document_id=document_id,
            target_user_id=target_user_id,
            request_id=request_id,
        )
    except Exception:
        logger.exception(
            "Audit hook failed while recording a denial",
            extra={"audit_action": action, "audit_persisted": False},
        )


@router.get(
    "/{document_id}/permissions",
    response_model=PermissionListResponse,
)
def list_permissions(
    document_id: uuid.UUID = Path(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    audit: UploadAuditHook = Depends(get_document_audit),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> PermissionListResponse:
    """List active grants for a document. Document owner only."""
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    try:
        document, grants = list_document_permissions(
            session,
            actor=current_user,
            document_id=document_id,
        )
    except DocumentAuthorizationError as exc:
        _safe_audit(
            audit,
            action="DOCUMENT_PERMISSION_LIST",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document_id,
            target_user_id=None,
            request_id=request_id,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    except DocumentSharingError as exc:
        _safe_audit(
            audit,
            action="DOCUMENT_PERMISSION_LIST",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document_id,
            target_user_id=None,
            request_id=request_id,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    try:
        audit_sharing_event(
            audit,
            action="DOCUMENT_PERMISSION_LIST",
            outcome="SUCCESS",
            reason_code=None,
            actor_id=current_user.id,
            document_id=document.id,
            target_user_id=None,
            request_id=request_id,
        )
    except Exception as exc:
        logger.exception("Audit failed after permission list")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Permission list could not be audited",
        ) from exc

    return PermissionListResponse(
        document_id=document.id,
        permissions=[_grant_response(g) for g in grants],
    )


@router.post(
    "/{document_id}/permissions",
    response_model=PermissionGrantResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_permission(
    body: PermissionGrantRequest,
    document_id: uuid.UUID = Path(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    audit: UploadAuditHook = Depends(get_document_audit),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> PermissionGrantResponse:
    """Grant READ or EDIT to an existing user. Document owner only.

    Client-supplied granted_by, revoked_at, owner_id, and audit fields are
    rejected via schema extra=forbid / ignored (not accepted).
    """
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    try:
        result = grant_document_permission(
            session,
            actor=current_user,
            document_id=document_id,
            target_user_id=body.user_id,
            permission=body.permission,
        )
    except DocumentAuthorizationError as exc:
        _safe_audit(
            audit,
            action="DOCUMENT_PERMISSION_GRANT",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document_id,
            target_user_id=body.user_id,
            request_id=request_id,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    except DocumentSharingError as exc:
        _safe_audit(
            audit,
            action="DOCUMENT_PERMISSION_GRANT",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document_id,
            target_user_id=body.user_id,
            request_id=request_id,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    reason = "REGRANTED" if result.regranted else None
    try:
        audit_sharing_event(
            audit,
            action="DOCUMENT_PERMISSION_GRANT",
            outcome="SUCCESS",
            reason_code=reason,
            actor_id=current_user.id,
            document_id=document_id,
            target_user_id=body.user_id,
            request_id=request_id,
        )
    except Exception as exc:
        # Undo only this grant — do not claim success if audit could not run.
        session.delete(result.grant)
        session.flush()
        logger.exception("Audit failed after grant; removing unaudited grant")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Grant could not be audited",
        ) from exc

    return _grant_response(result.grant, regranted=result.regranted)


@router.delete(
    "/{document_id}/permissions/{user_id}",
    response_model=PermissionRevokeResponse,
)
def delete_permission(
    document_id: uuid.UUID = Path(...),
    user_id: uuid.UUID = Path(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    audit: UploadAuditHook = Depends(get_document_audit),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> PermissionRevokeResponse:
    """Revoke an active grant (set revoked_at). Document owner only.

    Missing or already-revoked grants return 404. Grantees cannot revoke via
    this endpoint. ADMIN role alone cannot revoke.
    """
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    try:
        grant = revoke_document_permission(
            session,
            actor=current_user,
            document_id=document_id,
            target_user_id=user_id,
        )
    except DocumentAuthorizationError as exc:
        _safe_audit(
            audit,
            action="DOCUMENT_PERMISSION_REVOKE",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document_id,
            target_user_id=user_id,
            request_id=request_id,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    except DocumentSharingError as exc:
        _safe_audit(
            audit,
            action="DOCUMENT_PERMISSION_REVOKE",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document_id,
            target_user_id=user_id,
            request_id=request_id,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    assert grant.revoked_at is not None
    revoked_at = grant.revoked_at
    permission_value = grant.permission
    try:
        audit_sharing_event(
            audit,
            action="DOCUMENT_PERMISSION_REVOKE",
            outcome="SUCCESS",
            reason_code=None,
            actor_id=current_user.id,
            document_id=document_id,
            target_user_id=user_id,
            request_id=request_id,
        )
    except Exception as exc:
        grant.revoked_at = None
        session.flush()
        logger.exception("Audit failed after revoke; restoring active grant")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Revocation could not be audited",
        ) from exc

    return PermissionRevokeResponse(
        document_id=document_id,
        user_id=user_id,
        permission=permission_value,
        revoked_at=revoked_at,
    )
