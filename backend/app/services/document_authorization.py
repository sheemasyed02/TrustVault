"""Centralized document authorization.

Authentication answers: who is the caller?
Authorization answers: may this caller perform this action on this document?

Rules are evaluated from PostgreSQL state for every protected operation.
Client-supplied roles, owner IDs, permission claims, and token role claims
are never used as proof of access.

HTTP mapping used by route dependencies:
- 401: unauthenticated / inactive account (normally via get_current_user)
- 404: missing, soft-deleted, or inaccessible document (reduces enumeration)
- 403: authenticated principal can see the document exists for them but the
  specific action is not allowed (for example READ grant attempting delete)
- Fail closed on database/query failures (no access granted)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentPermission, User

logger = logging.getLogger(__name__)

# Fields that metadata-update APIs must never accept from clients.
PROTECTED_DOCUMENT_FIELDS = frozenset(
    {
        "id",
        "owner_id",
        "storage_key",
        "mime_type",
        "file_size",
        "sha256_checksum",
        "created_at",
        "updated_at",
        "deleted_at",
        "password_hash",
        "role",
        "permission",
        "granted_by",
        "revoked_at",
        "event_hash",
        "previous_hash",
    }
)

GENERIC_NOT_FOUND = "Document not found"
GENERIC_FORBIDDEN = "Forbidden"
GENERIC_UNAVAILABLE = "Authorization check failed"


class DocumentAction(str, Enum):
    READ = "read"  # metadata read and download
    EDIT_METADATA = "edit_metadata"  # owner only (title/category/description)
    EDIT_CONTENT = "edit_content"  # owner or active EDIT grant (file body)
    MANAGE_PERMISSIONS = "manage_permissions"  # grant / revoke
    DELETE = "delete"


class DocumentAuthorizationError(Exception):
    """Raised when a document action is denied or cannot be safely evaluated."""

    def __init__(
        self,
        *,
        status_code: int,
        detail: str,
        reason_code: str,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.reason_code = reason_code


class AuthorizationAuditHook(Protocol):
    """Integration point for the future audit trail.

    Implementations must never receive passwords, tokens, or file bytes.
    The current NullAuthorizationAuditHook does not persist events.
    """

    def record_denied(
        self,
        *,
        actor: User | None,
        document_id: uuid.UUID | None,
        action: DocumentAction,
        reason_code: str,
    ) -> None: ...

    def record_allowed(
        self,
        *,
        actor: User,
        document_id: uuid.UUID,
        action: DocumentAction,
    ) -> None: ...


class NullAuthorizationAuditHook:
    """No-op audit hook. Does not claim that events were persisted."""

    def record_denied(
        self,
        *,
        actor: User | None,
        document_id: uuid.UUID | None,
        action: DocumentAction,
        reason_code: str,
    ) -> None:
        logger.info(
            "Document authorization denied",
            extra={
                "authz_event": "denied",
                "authz_action": action.value,
                "authz_reason": reason_code,
            },
        )

    def record_allowed(
        self,
        *,
        actor: User,
        document_id: uuid.UUID,
        action: DocumentAction,
    ) -> None:
        logger.info(
            "Document authorization allowed",
            extra={
                "authz_event": "allowed",
                "authz_action": action.value,
            },
        )


@dataclass(frozen=True, slots=True)
class DocumentAccessContext:
    """Result of a successful authorization check."""

    document: Document
    user: User
    is_owner: bool
    grant_permission: str | None  # "READ", "EDIT", or None for owner


_DEFAULT_AUDIT: AuthorizationAuditHook = NullAuthorizationAuditHook()


def reject_protected_metadata_fields(payload: dict) -> None:
    """Reject client attempts to set protected internal document fields."""
    illegal = sorted(PROTECTED_DOCUMENT_FIELDS.intersection(payload.keys()))
    if illegal:
        raise DocumentAuthorizationError(
            status_code=400,
            detail="Invalid document fields",
            reason_code="PROTECTED_FIELD_REJECTED",
        )


def _deny(
    *,
    audit: AuthorizationAuditHook,
    actor: User | None,
    document_id: uuid.UUID | None,
    action: DocumentAction,
    status_code: int,
    detail: str,
    reason_code: str,
) -> None:
    audit.record_denied(
        actor=actor,
        document_id=document_id,
        action=action,
        reason_code=reason_code,
    )
    raise DocumentAuthorizationError(
        status_code=status_code,
        detail=detail,
        reason_code=reason_code,
    )


def _active_grant(
    session: Session,
    *,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
) -> DocumentPermission | None:
    grants = list(
        session.scalars(
            select(DocumentPermission).where(
                DocumentPermission.document_id == document_id,
                DocumentPermission.user_id == user_id,
                DocumentPermission.revoked_at.is_(None),
            )
        ).all()
    )
    if len(grants) > 1:
        # Unique index should prevent this; fail closed if data is ambiguous.
        raise DocumentAuthorizationError(
            status_code=503,
            detail=GENERIC_UNAVAILABLE,
            reason_code="AMBIGUOUS_ACTIVE_GRANTS",
        )
    if not grants:
        return None
    grant = grants[0]
    if grant.permission not in {"READ", "EDIT"}:
        raise DocumentAuthorizationError(
            status_code=503,
            detail=GENERIC_UNAVAILABLE,
            reason_code="INVALID_GRANT_PERMISSION",
        )
    return grant


def _action_allowed(
    *,
    is_owner: bool,
    grant_permission: str | None,
    action: DocumentAction,
) -> bool:
    if is_owner:
        return True
    if grant_permission == "EDIT":
        # EDIT grants view/download and content edits only — not metadata,
        # sharing, ownership, or delete.
        return action in {DocumentAction.READ, DocumentAction.EDIT_CONTENT}
    if grant_permission == "READ":
        return action == DocumentAction.READ
    return False


def evaluate_document_access(
    session: Session,
    *,
    user: User,
    document_id: uuid.UUID,
    action: DocumentAction,
    audit: AuthorizationAuditHook | None = None,
) -> DocumentAccessContext:
    """Authorize a document action using current database state.

    ADMIN role alone never grants document-content access.
    """
    hook = audit or _DEFAULT_AUDIT

    if user is None or not user.is_active:
        _deny(
            audit=hook,
            actor=user,
            document_id=document_id,
            action=action,
            status_code=401,
            detail="Not authenticated",
            reason_code="INACTIVE_OR_MISSING_USER",
        )

    try:
        document = session.get(Document, document_id)
    except SQLAlchemyError:
        logger.error(
            "Document authorization query failed",
            extra={"authz_event": "query_failed", "authz_action": action.value},
        )
        _deny(
            audit=hook,
            actor=user,
            document_id=document_id,
            action=action,
            status_code=503,
            detail=GENERIC_UNAVAILABLE,
            reason_code="AUTHORIZATION_QUERY_FAILED",
        )

    if document is None or document.deleted_at is not None:
        _deny(
            audit=hook,
            actor=user,
            document_id=document_id,
            action=action,
            status_code=404,
            detail=GENERIC_NOT_FOUND,
            reason_code="DOCUMENT_MISSING_OR_DELETED",
        )

    is_owner = document.owner_id == user.id
    grant_permission: str | None = None

    if not is_owner:
        try:
            grant = _active_grant(
                session,
                document_id=document.id,
                user_id=user.id,
            )
        except DocumentAuthorizationError as exc:
            if exc.reason_code in {
                "AMBIGUOUS_ACTIVE_GRANTS",
                "INVALID_GRANT_PERMISSION",
            }:
                hook.record_denied(
                    actor=user,
                    document_id=document.id,
                    action=action,
                    reason_code=exc.reason_code,
                )
            raise
        except SQLAlchemyError:
            logger.error(
                "Document grant query failed",
                extra={"authz_event": "query_failed", "authz_action": action.value},
            )
            _deny(
                audit=hook,
                actor=user,
                document_id=document.id,
                action=action,
                status_code=503,
                detail=GENERIC_UNAVAILABLE,
                reason_code="AUTHORIZATION_QUERY_FAILED",
            )

        if grant is None:
            # ADMIN without a grant is treated like any other unauthorized user.
            _deny(
                audit=hook,
                actor=user,
                document_id=document.id,
                action=action,
                status_code=404,
                detail=GENERIC_NOT_FOUND,
                reason_code="NO_ACTIVE_GRANT",
            )
        grant_permission = grant.permission

    if not _action_allowed(
        is_owner=is_owner,
        grant_permission=grant_permission,
        action=action,
    ):
        # Principal has some relationship to the document but not this action.
        _deny(
            audit=hook,
            actor=user,
            document_id=document.id,
            action=action,
            status_code=403,
            detail=GENERIC_FORBIDDEN,
            reason_code="ACTION_NOT_PERMITTED",
        )

    context = DocumentAccessContext(
        document=document,
        user=user,
        is_owner=is_owner,
        grant_permission=grant_permission,
    )
    hook.record_allowed(
        actor=user,
        document_id=document.id,
        action=action,
    )
    return context


def caller_access_level(context: DocumentAccessContext) -> str:
    """Return document-level access for API/UI capability hints.

    Values are ``OWNER`` (document owner via ``documents.owner_id``), ``EDIT``,
    or ``READ`` (active grant). These are **not** platform roles
    (``users.role`` ADMIN/OWNER/VIEWER). A grant never promotes a user to
    platform OWNER or ADMIN.
    """
    if context.is_owner:
        return "OWNER"
    if context.grant_permission == "EDIT":
        return "EDIT"
    return "READ"


def require_document_read(
    session: Session,
    *,
    user: User,
    document_id: uuid.UUID,
    audit: AuthorizationAuditHook | None = None,
) -> Document:
    """Require ownership or an active READ/EDIT grant (includes download)."""
    return evaluate_document_access(
        session,
        user=user,
        document_id=document_id,
        action=DocumentAction.READ,
        audit=audit,
    ).document


def require_document_read_context(
    session: Session,
    *,
    user: User,
    document_id: uuid.UUID,
    audit: AuthorizationAuditHook | None = None,
) -> DocumentAccessContext:
    """Like require_document_read, but keep ownership/grant details for the response."""
    return evaluate_document_access(
        session,
        user=user,
        document_id=document_id,
        action=DocumentAction.READ,
        audit=audit,
    )


def require_document_edit(
    session: Session,
    *,
    user: User,
    document_id: uuid.UUID,
    audit: AuthorizationAuditHook | None = None,
) -> Document:
    """Require document ownership for title/category/description edits."""
    return evaluate_document_access(
        session,
        user=user,
        document_id=document_id,
        action=DocumentAction.EDIT_METADATA,
        audit=audit,
    ).document


def require_document_edit_context(
    session: Session,
    *,
    user: User,
    document_id: uuid.UUID,
    audit: AuthorizationAuditHook | None = None,
) -> DocumentAccessContext:
    """Like require_document_edit, but keep ownership/grant details for the response."""
    return evaluate_document_access(
        session,
        user=user,
        document_id=document_id,
        action=DocumentAction.EDIT_METADATA,
        audit=audit,
    )


def require_document_content_edit(
    session: Session,
    *,
    user: User,
    document_id: uuid.UUID,
    audit: AuthorizationAuditHook | None = None,
) -> Document:
    """Require ownership or an active EDIT grant for document body edits."""
    return evaluate_document_access(
        session,
        user=user,
        document_id=document_id,
        action=DocumentAction.EDIT_CONTENT,
        audit=audit,
    ).document


def require_document_content_edit_context(
    session: Session,
    *,
    user: User,
    document_id: uuid.UUID,
    audit: AuthorizationAuditHook | None = None,
) -> DocumentAccessContext:
    """Like require_document_content_edit, keeping ownership/grant details."""
    return evaluate_document_access(
        session,
        user=user,
        document_id=document_id,
        action=DocumentAction.EDIT_CONTENT,
        audit=audit,
    )


def require_document_owner(
    session: Session,
    *,
    user: User,
    document_id: uuid.UUID,
    audit: AuthorizationAuditHook | None = None,
) -> Document:
    """Require document ownership (share/revoke/delete and similar)."""
    return evaluate_document_access(
        session,
        user=user,
        document_id=document_id,
        action=DocumentAction.MANAGE_PERMISSIONS,
        audit=audit,
    ).document


def require_document_delete(
    session: Session,
    *,
    user: User,
    document_id: uuid.UUID,
    audit: AuthorizationAuditHook | None = None,
) -> Document:
    """Owner-only soft-delete policy check for future delete endpoints."""
    return evaluate_document_access(
        session,
        user=user,
        document_id=document_id,
        action=DocumentAction.DELETE,
        audit=audit,
    ).document
