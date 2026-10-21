"""Secure document upload orchestration (validate → R2 → PostgreSQL).

Order of operations:
1. Authorize OWNER from database-backed role.
2. Validate metadata and file bytes (size, type, structure, checksum).
3. Upload to private R2 under a server-generated opaque key.
4. Insert the document row in PostgreSQL.
5. If the DB commit fails after R2 success, attempt to delete the R2 object.

Residual risk: if R2 upload succeeds, DB insert fails, and R2 cleanup also
fails, an orphaned private object may remain until operational cleanup.
Success is never returned in that case.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Document, User
from app.services.file_validation import (
    FileValidationError,
    ValidatedUpload,
    validate_upload_bytes,
)
from app.services.upload_audit import NullUploadAuditHook, UploadAuditHook
from app.storage import R2StorageService, StorageError, generate_object_key
from app.storage.hashing import sha256_hex_bytes

logger = logging.getLogger(__name__)

MAX_TITLE_LENGTH = 255
MAX_CATEGORY_LENGTH = 128
MAX_DESCRIPTION_LENGTH = 5000


class DocumentUploadError(Exception):
    def __init__(self, message: str, *, status_code: int, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class UploadedDocumentResult:
    document: Document
    media_type: str
    size_bytes: int
    sha256_hex: str


def normalize_title(title: str) -> str:
    cleaned = (title or "").strip()
    if not cleaned:
        raise DocumentUploadError(
            "Title is required",
            status_code=422,
            reason_code="TITLE_REQUIRED",
        )
    if len(cleaned) > MAX_TITLE_LENGTH:
        raise DocumentUploadError(
            "Title is too long",
            status_code=422,
            reason_code="TITLE_TOO_LONG",
        )
    return cleaned


def normalize_category(category: str) -> str:
    cleaned = (category or "").strip()
    if not cleaned:
        raise DocumentUploadError(
            "Category is required",
            status_code=422,
            reason_code="CATEGORY_REQUIRED",
        )
    if len(cleaned) > MAX_CATEGORY_LENGTH:
        raise DocumentUploadError(
            "Category is too long",
            status_code=422,
            reason_code="CATEGORY_TOO_LONG",
        )
    return cleaned


def normalize_description(description: str | None) -> str | None:
    if description is None:
        return None
    cleaned = description.strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_DESCRIPTION_LENGTH:
        raise DocumentUploadError(
            "Description is too long",
            status_code=422,
            reason_code="DESCRIPTION_TOO_LONG",
        )
    return cleaned


def require_owner_uploader(user: User, *, audit: UploadAuditHook) -> None:
    if user.role != "OWNER":
        audit.record(
            action="DOCUMENT_UPLOAD",
            outcome="DENIED",
            reason_code="ROLE_NOT_OWNER",
            actor_id=user.id,
        )
        raise DocumentUploadError(
            "Forbidden",
            status_code=403,
            reason_code="ROLE_NOT_OWNER",
        )


def upload_document(
    session: Session,
    *,
    owner: User,
    file_bytes: bytes,
    filename: str | None,
    client_content_type: str | None,
    title: str,
    category: str,
    description: str | None,
    storage: R2StorageService,
    audit: UploadAuditHook | None = None,
    request_id: str | None = None,
) -> UploadedDocumentResult:
    hook = audit or NullUploadAuditHook()
    require_owner_uploader(owner, audit=hook)

    try:
        clean_title = normalize_title(title)
        clean_category = normalize_category(category)
        clean_description = normalize_description(description)
        digest = sha256_hex_bytes(file_bytes)
        validated: ValidatedUpload = validate_upload_bytes(
            file_bytes,
            filename=filename,
            client_content_type=client_content_type,
            sha256_hex=digest,
        )
    except FileValidationError as exc:
        hook.record(
            action="DOCUMENT_UPLOAD",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=owner.id,
            request_id=request_id,
        )
        raise DocumentUploadError(
            exc.message,
            status_code=exc.status_code,
            reason_code=exc.reason_code,
        ) from None
    except DocumentUploadError as exc:
        hook.record(
            action="DOCUMENT_UPLOAD",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=owner.id,
            request_id=request_id,
        )
        raise

    storage_key = generate_object_key(prefix="objects")
    document_id = uuid.uuid4()

    try:
        storage.upload_bytes(
            storage_key,
            file_bytes,
            content_type=validated.media_type,
            expected_sha256=validated.sha256_hex,
        )
    except StorageError:
        logger.error(
            "Document upload storage failure",
            extra={"upload_stage": "r2_put", "upload_request_id": request_id},
        )
        hook.record(
            action="DOCUMENT_UPLOAD",
            outcome="DENIED",
            reason_code="STORAGE_UPLOAD_FAILED",
            actor_id=owner.id,
            request_id=request_id,
        )
        raise DocumentUploadError(
            "Document storage failed",
            status_code=500,
            reason_code="STORAGE_UPLOAD_FAILED",
        ) from None

    document = Document(
        id=document_id,
        owner_id=owner.id,
        title=clean_title,
        category=clean_category,
        description=clean_description,
        storage_key=storage_key,
        original_filename=validated.original_filename,
        mime_type=validated.media_type,
        file_size=validated.size_bytes,
        sha256_checksum=validated.sha256_hex,
        deleted_at=None,
    )
    session.add(document)

    try:
        session.flush()
    except SQLAlchemyError:
        logger.error(
            "Document upload database failure after storage put",
            extra={"upload_stage": "db_insert", "upload_request_id": request_id},
        )
        cleanup_ok = _compensate_storage_delete(storage, storage_key, request_id)
        hook.record(
            action="DOCUMENT_UPLOAD",
            outcome="DENIED",
            reason_code=(
                "DB_INSERT_FAILED_CLEANUP_OK"
                if cleanup_ok
                else "DB_INSERT_FAILED_CLEANUP_FAILED"
            ),
            actor_id=owner.id,
            request_id=request_id,
        )
        raise DocumentUploadError(
            "Document persistence failed",
            status_code=500,
            reason_code="DB_INSERT_FAILED",
        ) from None

    hook.record(
        action="DOCUMENT_UPLOAD",
        outcome="SUCCESS",
        reason_code=None,
        actor_id=owner.id,
        document_id=document.id,
        request_id=request_id,
    )
    logger.info(
        "Document upload succeeded",
        extra={
            "upload_stage": "complete",
            "upload_size": validated.size_bytes,
            "upload_request_id": request_id,
        },
    )
    return UploadedDocumentResult(
        document=document,
        media_type=validated.media_type,
        size_bytes=validated.size_bytes,
        sha256_hex=validated.sha256_hex,
    )


def _compensate_storage_delete(
    storage: R2StorageService,
    storage_key: str,
    request_id: str | None,
) -> bool:
    try:
        storage.delete_object(storage_key)
        logger.info(
            "Compensating storage delete succeeded",
            extra={"upload_stage": "r2_compensate", "upload_request_id": request_id},
        )
        return True
    except StorageError:
        logger.error(
            "Compensating storage delete failed; orphaned private object may remain",
            extra={"upload_stage": "r2_compensate_failed", "upload_request_id": request_id},
        )
        return False
