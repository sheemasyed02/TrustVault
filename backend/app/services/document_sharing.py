"""Owner-controlled document sharing: list, grant, and revoke READ/EDIT access.

Active grants: document_permissions.revoked_at IS NULL.
Revocation: set revoked_at (history retained). Regrant creates a new row after
an explicit owner request — never silently clears revoked_at on an old row.

Each protected document request (list/metadata/download/edit) re-queries
PostgreSQL via document_authorization; grants are not cached in JWTs.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.db.models import Document, DocumentPermission, User
from app.services.document_authorization import require_document_owner
from app.services.upload_audit import UploadAuditHook

logger = logging.getLogger(__name__)

ALLOWED_PERMISSIONS = frozenset({"READ", "EDIT"})


class DocumentSharingError(Exception):
    def __init__(self, message: str, *, status_code: int, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class GrantResult:
    grant: DocumentPermission
    regranted: bool


def _load_active_grants(
    session: Session,
    *,
    document_id: uuid.UUID,
) -> list[DocumentPermission]:
    return list(
        session.scalars(
            select(DocumentPermission)
            .options(
                joinedload(DocumentPermission.user),
                joinedload(DocumentPermission.grantor),
            )
            .where(
                DocumentPermission.document_id == document_id,
                DocumentPermission.revoked_at.is_(None),
            )
            .order_by(DocumentPermission.created_at.asc(), DocumentPermission.id.asc())
        )
        .unique()
        .all()
    )


def list_document_permissions(
    session: Session,
    *,
    actor: User,
    document_id: uuid.UUID,
) -> tuple[Document, list[DocumentPermission]]:
    """Return active grants for a document. Owner-only."""
    document = require_document_owner(
        session,
        user=actor,
        document_id=document_id,
    )
    try:
        grants = _load_active_grants(session, document_id=document.id)
    except SQLAlchemyError as exc:
        logger.error("Failed to list document permissions")
        raise DocumentSharingError(
            "Unable to list permissions",
            status_code=503,
            reason_code="PERMISSION_LIST_QUERY_FAILED",
        ) from exc
    return document, grants


def grant_document_permission(
    session: Session,
    *,
    actor: User,
    document_id: uuid.UUID,
    target_user_id: uuid.UUID,
    permission: str,
) -> GrantResult:
    """Create an active READ/EDIT grant. Owner-only. granted_by = actor."""
    document = require_document_owner(
        session,
        user=actor,
        document_id=document_id,
    )

    normalized = (permission or "").strip().upper()
    if normalized not in ALLOWED_PERMISSIONS:
        raise DocumentSharingError(
            "permission must be READ or EDIT",
            status_code=422,
            reason_code="INVALID_PERMISSION_VALUE",
        )

    if target_user_id == document.owner_id:
        raise DocumentSharingError(
            "Cannot grant access to the document owner",
            status_code=400,
            reason_code="CANNOT_GRANT_TO_OWNER",
        )

    try:
        target = session.get(User, target_user_id)
    except SQLAlchemyError as exc:
        raise DocumentSharingError(
            "Unable to resolve target user",
            status_code=503,
            reason_code="TARGET_USER_QUERY_FAILED",
        ) from exc

    if target is None:
        raise DocumentSharingError(
            "User not found",
            status_code=404,
            reason_code="TARGET_USER_NOT_FOUND",
        )
    if not target.is_active:
        raise DocumentSharingError(
            "Target user is inactive",
            status_code=400,
            reason_code="TARGET_USER_INACTIVE",
        )

    existing_active = session.scalar(
        select(DocumentPermission).where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.user_id == target.id,
            DocumentPermission.revoked_at.is_(None),
        )
    )
    if existing_active is not None:
        raise DocumentSharingError(
            "An active grant already exists for this user",
            status_code=409,
            reason_code="DUPLICATE_ACTIVE_GRANT",
        )

    prior_revoked = session.scalar(
        select(DocumentPermission)
        .where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.user_id == target.id,
            DocumentPermission.revoked_at.is_not(None),
        )
        .order_by(DocumentPermission.revoked_at.desc())
        .limit(1)
    )
    regranted = prior_revoked is not None

    grant = DocumentPermission(
        document_id=document.id,
        user_id=target.id,
        permission=normalized,
        granted_by=actor.id,
        revoked_at=None,
    )
    try:
        # Savepoint so a concurrent unique-index collision does not poison
        # the outer request/test transaction.
        with session.begin_nested():
            session.add(grant)
            session.flush()
    except IntegrityError as exc:
        # Concurrent duplicate active grant (partial unique index).
        raise DocumentSharingError(
            "An active grant already exists for this user",
            status_code=409,
            reason_code="DUPLICATE_ACTIVE_GRANT",
        ) from exc
    except SQLAlchemyError as exc:
        logger.error("Failed to create document permission")
        raise DocumentSharingError(
            "Unable to grant permission",
            status_code=503,
            reason_code="GRANT_PERSIST_FAILED",
        ) from exc

    # Reload relationships for safe serialization.
    session.refresh(grant)
    grant = session.scalars(
        select(DocumentPermission)
        .options(
            joinedload(DocumentPermission.user),
            joinedload(DocumentPermission.grantor),
        )
        .where(DocumentPermission.id == grant.id)
    ).unique().one()
    return GrantResult(grant=grant, regranted=regranted)


def revoke_document_permission(
    session: Session,
    *,
    actor: User,
    document_id: uuid.UUID,
    target_user_id: uuid.UUID,
) -> DocumentPermission:
    """Soft-revoke the active grant for target_user_id. Owner-only."""
    document = require_document_owner(
        session,
        user=actor,
        document_id=document_id,
    )

    try:
        grant = session.scalar(
            select(DocumentPermission).where(
                DocumentPermission.document_id == document.id,
                DocumentPermission.user_id == target_user_id,
                DocumentPermission.revoked_at.is_(None),
            )
        )
    except SQLAlchemyError as exc:
        raise DocumentSharingError(
            "Unable to revoke permission",
            status_code=503,
            reason_code="REVOKE_QUERY_FAILED",
        ) from exc

    if grant is None:
        raise DocumentSharingError(
            "Active grant not found",
            status_code=404,
            reason_code="ACTIVE_GRANT_NOT_FOUND",
        )

    grant.revoked_at = datetime.now(timezone.utc)
    try:
        with session.begin_nested():
            session.flush()
    except SQLAlchemyError as exc:
        logger.error("Failed to revoke document permission")
        raise DocumentSharingError(
            "Unable to revoke permission",
            status_code=503,
            reason_code="REVOKE_PERSIST_FAILED",
        ) from exc

    return grant


def audit_sharing_event(
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
    """Record a sharing audit event; never claim durable persistence here."""
    audit.record(
        action=action,
        outcome=outcome,
        reason_code=reason_code,
        actor_id=actor_id,
        document_id=document_id,
        target_user_id=target_user_id,
        request_id=request_id,
    )
