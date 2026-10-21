"""Owner-only soft-delete with best-effort private R2 cleanup.

Strategy (not a distributed transaction):
1. Authorize owner via require_document_delete.
2. Soft-delete in PostgreSQL (set deleted_at) so list/read/download deny immediately.
3. Delete the R2 object using the server-side storage_key only.
4. If R2 delete succeeds (or object already absent) → success.
5. If R2 delete fails after soft-delete → keep soft-deleted (unservable),
   audit STORAGE_DELETE_FAILED, return failure (never claim complete deletion).

Residual risk: soft-deleted DB row with an orphaned private R2 object until a
retry deletes it. Permission and audit history rows are retained.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Document, User
from app.services.document_authorization import require_document_delete
from app.storage import R2StorageService, StorageError, StorageNotFoundError

logger = logging.getLogger(__name__)


class DocumentDeletionError(Exception):
    def __init__(self, message: str, *, status_code: int, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class DocumentDeletionResult:
    document: Document
    storage_cleanup: str  # "completed" | "already_absent"


def soft_delete_document(
    session: Session,
    *,
    actor: User,
    document_id: uuid.UUID,
    storage: R2StorageService,
) -> DocumentDeletionResult:
    document = require_document_delete(
        session,
        user=actor,
        document_id=document_id,
    )
    storage_key = document.storage_key

    document.deleted_at = datetime.now(timezone.utc)
    document.updated_at = datetime.now(timezone.utc)
    try:
        session.flush()
    except SQLAlchemyError as exc:
        logger.error("Failed to soft-delete document in database")
        raise DocumentDeletionError(
            "Unable to delete document",
            status_code=503,
            reason_code="DB_DELETE_FAILED",
        ) from exc

    try:
        storage.delete_object(storage_key)
        cleanup = "completed"
    except StorageNotFoundError:
        # Idempotent: object already gone; catalog tombstone is enough.
        cleanup = "already_absent"
        logger.info(
            "R2 object already absent during document delete",
            extra={"delete_stage": "r2_absent"},
        )
    except StorageError as exc:
        logger.error(
            "R2 delete failed after soft-delete; object may remain private orphan",
            extra={"delete_stage": "r2_delete_failed"},
        )
        # Persist the tombstone before the request fails — get_db rolls back on
        # exceptions, which would otherwise revive a document that must stay gone.
        try:
            session.commit()
        except SQLAlchemyError:
            logger.error("Failed to commit soft-delete after storage cleanup failure")
        raise DocumentDeletionError(
            "Document removed from catalog but storage cleanup failed",
            status_code=503,
            reason_code="STORAGE_DELETE_FAILED",
        ) from exc

    return DocumentDeletionResult(document=document, storage_cleanup=cleanup)
