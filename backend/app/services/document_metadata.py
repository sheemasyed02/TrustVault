"""Authorized document metadata updates (title, category, description only)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.db.models import Document, DocumentPermission, User
from app.services.document_authorization import (
    DocumentAction,
    DocumentAuthorizationError,
    evaluate_document_access,
    reject_protected_metadata_fields,
)
from app.services.document_upload import (
    DocumentUploadError,
    normalize_category,
    normalize_description,
    normalize_title,
)

logger = logging.getLogger(__name__)


class DocumentMetadataError(Exception):
    def __init__(self, message: str, *, status_code: int, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class MetadataUpdateResult:
    document: Document
    changed_fields: list[str]


def update_document_metadata(
    session: Session,
    *,
    actor: User,
    document_id: uuid.UUID,
    fields: dict,
) -> MetadataUpdateResult:
    """Apply a partial metadata update after re-checking EDIT authorization.

    Transaction policy: the document row is locked with FOR UPDATE, then edit
    authorization is re-evaluated against current grants. A revoke committed
    before this transaction's grant check will deny the edit. Concurrent revoke
    after the check but before commit remains a small residual race under
    READ COMMITTED (documented; not claimed as fully eliminated).
    """
    reject_protected_metadata_fields(fields)

    allowed = {"title", "category", "description"}
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise DocumentMetadataError(
            "Unsupported fields",
            status_code=422,
            reason_code="UNSUPPORTED_FIELDS",
        )

    try:
        locked = session.scalars(
            select(Document).where(Document.id == document_id).with_for_update()
        ).one_or_none()
    except SQLAlchemyError as exc:
        logger.error("Failed to lock document for metadata update")
        raise DocumentMetadataError(
            "Unable to update document",
            status_code=503,
            reason_code="DOCUMENT_LOCK_FAILED",
        ) from exc

    if locked is None or locked.deleted_at is not None:
        raise DocumentAuthorizationError(
            status_code=404,
            detail="Document not found",
            reason_code="DOCUMENT_MISSING_OR_DELETED",
        )

    # Re-check edit rights after the row lock (current grant state).
    evaluate_document_access(
        session,
        user=actor,
        document_id=document_id,
        action=DocumentAction.EDIT_METADATA,
    )

    # If the actor is not the owner, lock their active grant row as well.
    if locked.owner_id != actor.id:
        try:
            session.scalars(
                select(DocumentPermission).where(
                    DocumentPermission.document_id == locked.id,
                    DocumentPermission.user_id == actor.id,
                    DocumentPermission.revoked_at.is_(None),
                ).with_for_update()
            ).one_or_none()
        except SQLAlchemyError as exc:
            raise DocumentMetadataError(
                "Unable to update document",
                status_code=503,
                reason_code="GRANT_LOCK_FAILED",
            ) from exc
        # Re-evaluate after grant lock in case of concurrent revoke.
        evaluate_document_access(
            session,
            user=actor,
            document_id=document_id,
            action=DocumentAction.EDIT_METADATA,
        )

    changed: list[str] = []
    try:
        if "title" in fields:
            new_title = normalize_title(fields["title"])
            if new_title != locked.title:
                locked.title = new_title
                changed.append("title")
        if "category" in fields:
            new_category = normalize_category(fields["category"])
            if new_category != locked.category:
                locked.category = new_category
                changed.append("category")
        if "description" in fields:
            new_description = normalize_description(fields["description"])
            if new_description != locked.description:
                locked.description = new_description
                changed.append("description")
    except DocumentUploadError as exc:
        raise DocumentMetadataError(
            exc.message,
            status_code=exc.status_code,
            reason_code=exc.reason_code,
        ) from None

    if changed:
        locked.updated_at = datetime.now(timezone.utc)
        try:
            session.flush()
        except SQLAlchemyError as exc:
            logger.error("Failed to persist metadata update")
            raise DocumentMetadataError(
                "Unable to update document",
                status_code=503,
                reason_code="METADATA_PERSIST_FAILED",
            ) from exc

    document = session.scalars(
        select(Document)
        .options(joinedload(Document.owner))
        .where(Document.id == locked.id)
    ).unique().one()
    return MetadataUpdateResult(document=document, changed_fields=changed)
