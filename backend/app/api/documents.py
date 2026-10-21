"""Document HTTP routes — upload, list, metadata, and authorized download."""

from __future__ import annotations

import logging
import math
import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Path,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.db.models import Document, User
from app.db.session import get_db
from app.schemas.documents import (
    DocumentContentUpdateRequest,
    DocumentCreatedResponse,
    DocumentDeleteResponse,
    DocumentDetailResponse,
    DocumentListItem,
    DocumentListResponse,
    DocumentMetadataUpdateRequest,
    DocumentOwnerSummary,
)
from app.services.document_authorization import (
    DocumentAuthorizationError,
    caller_access_level,
    require_document_read,
    require_document_read_context,
)
from app.services.document_content import (
    DocumentContentError,
    replace_document_text_content,
)
from app.services.document_deletion import (
    DocumentDeletionError,
    soft_delete_document,
)
from app.services.document_download import (
    DownloadStorageError,
    open_download_stream,
    safe_download_filename,
)
from app.services.document_listing import (
    DocumentListValidationError,
    list_accessible_documents,
    validate_list_filters,
)
from app.services.document_metadata import (
    DocumentMetadataError,
    update_document_metadata,
)
from app.services.document_upload import DocumentUploadError, upload_document
from app.services.file_validation import MAX_UPLOAD_BYTES
from app.services.upload_audit import DurableAuditHook, UploadAuditHook
from app.storage import R2StorageService, StorageError, get_storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

_CHUNK_SIZE = 1024 * 1024
_DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def get_storage() -> R2StorageService:
    return get_storage_service()


def get_upload_audit(session: Session = Depends(get_db)) -> UploadAuditHook:
    """Durable hash-chain writer bound to the request session for SUCCESS events."""
    return DurableAuditHook(session)


def get_document_audit(session: Session = Depends(get_db)) -> UploadAuditHook:
    """Durable hash-chain writer for list/metadata/download/delete outcomes."""
    return DurableAuditHook(session)


async def _read_upload_with_limit(upload: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="File exceeds the 10 MiB size limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _owner_summary(document: Document) -> DocumentOwnerSummary:
    return DocumentOwnerSummary.model_validate(document.owner)


def _detail_response(document: Document, *, your_access: str) -> DocumentDetailResponse:
    return DocumentDetailResponse(
        id=document.id,
        title=document.title,
        category=document.category,
        description=document.description,
        owner=_owner_summary(document),
        original_filename=document.original_filename,
        mime_type=document.mime_type,
        file_size=document.file_size,
        sha256_checksum=document.sha256_checksum,
        created_at=document.created_at,
        updated_at=document.updated_at,
        your_access=your_access,
    )


@router.post(
    "",
    response_model=DocumentCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_document(
    title: str = Form(...),
    category: str = Form(...),
    description: str | None = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    storage: R2StorageService = Depends(get_storage),
    audit: UploadAuditHook = Depends(get_upload_audit),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> DocumentCreatedResponse:
    """Upload a document to private R2 and persist metadata for the OWNER.

    Client-supplied owner_id, storage_key, checksum, size, and audit fields are
    ignored because they are not accepted as form parameters.
    """
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())

    # Deny non-OWNER before accepting large bodies into memory.
    if current_user.role != "OWNER":
        audit.record(
            action="DOCUMENT_UPLOAD",
            outcome="DENIED",
            reason_code="ROLE_NOT_OWNER",
            actor_id=current_user.id,
            request_id=request_id,
        )
        await file.close()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        file_bytes = await _read_upload_with_limit(file)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_413_CONTENT_TOO_LARGE:
            audit.record(
                action="DOCUMENT_UPLOAD",
                outcome="DENIED",
                reason_code="FILE_TOO_LARGE",
                actor_id=current_user.id,
                request_id=request_id,
            )
        raise
    finally:
        await file.close()

    try:
        result = upload_document(
            session,
            owner=current_user,
            file_bytes=file_bytes,
            filename=file.filename,
            client_content_type=file.content_type,
            title=title,
            category=category,
            description=description,
            storage=storage,
            audit=audit,
            request_id=request_id,
        )
        session.refresh(result.document)
    except DocumentUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    document = result.document
    return DocumentCreatedResponse(
        id=document.id,
        title=document.title,
        category=document.category,
        description=document.description,
        owner=DocumentOwnerSummary.model_validate(current_user),
        original_filename=document.original_filename,
        mime_type=document.mime_type,
        file_size=document.file_size,
        sha256_checksum=document.sha256_checksum,
        created_at=document.created_at,
    )


@router.get("", response_model=DocumentListResponse)
def list_documents(
    title: str | None = Query(default=None, description="Case-insensitive title search"),
    owner_id: uuid.UUID | None = Query(default=None),
    owner_email: str | None = Query(default=None),
    category: str | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    shared_only: bool = Query(
        default=False,
        description="When true, return only documents shared with the caller (not owned)",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    audit: UploadAuditHook = Depends(get_document_audit),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> DocumentListResponse:
    """Paginated list of documents the caller may discover.

    Visibility is ownership or an active READ/EDIT grant. ADMIN role alone does
    not expand the result set. Filters never reveal inaccessible documents.
    Each row includes ``your_access`` (OWNER | EDIT | READ) from PostgreSQL.
    """
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    try:
        filters = validate_list_filters(
            title=title,
            owner_id=owner_id,
            owner_email=owner_email,
            category=category,
            created_from=created_from,
            created_to=created_to,
            shared_only=shared_only,
            page=page,
            page_size=page_size,
        )
    except DocumentListValidationError as exc:
        audit.record(
            action="DOCUMENT_LIST",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            request_id=request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.message,
        ) from None

    result = list_accessible_documents(session, user=current_user, filters=filters)

    audit.record(
        action="DOCUMENT_LIST",
        outcome="SUCCESS",
        reason_code=None,
        actor_id=current_user.id,
        request_id=request_id,
    )
    total_pages = math.ceil(result.total / result.page_size) if result.total else 0
    rows: list[DocumentListItem] = []
    for doc in result.items:
        access = result.access_by_document_id.get(doc.id)
        if access is None:
            # Fail closed: never return a row without a resolved access level.
            continue
        rows.append(
            DocumentListItem(
                id=doc.id,
                title=doc.title,
                category=doc.category,
                owner=_owner_summary(doc),
                original_filename=doc.original_filename,
                mime_type=doc.mime_type,
                file_size=doc.file_size,
                created_at=doc.created_at,
                your_access=access,
            )
        )
    return DocumentListResponse(
        results=rows,
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        total_pages=total_pages,
    )


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document_metadata(
    document_id: uuid.UUID = Path(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    audit: UploadAuditHook = Depends(get_document_audit),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> DocumentDetailResponse:
    """Return safe metadata after centralized read authorization.

    Includes `your_access` (OWNER | EDIT | READ) so the UI can show edit vs
    read-only controls without trusting client role claims.
    """
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    try:
        access_ctx = require_document_read_context(
            session,
            user=current_user,
            document_id=document_id,
        )
    except DocumentAuthorizationError as exc:
        audit.record(
            action="DOCUMENT_METADATA_READ",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document_id,
            request_id=request_id,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None

    your_access = caller_access_level(access_ctx)

    # Reload with owner for response; storage_key must never be serialized.
    document = session.scalars(
        select(Document)
        .options(joinedload(Document.owner))
        .where(Document.id == access_ctx.document.id)
    ).unique().one_or_none()
    if document is None:
        audit.record(
            action="DOCUMENT_METADATA_READ",
            outcome="DENIED",
            reason_code="DOCUMENT_MISSING",
            actor_id=current_user.id,
            document_id=document_id,
            request_id=request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    audit.record(
        action="DOCUMENT_METADATA_READ",
        outcome="SUCCESS",
        reason_code=None,
        actor_id=current_user.id,
        document_id=document.id,
        request_id=request_id,
    )
    return _detail_response(document, your_access=your_access)


@router.patch("/{document_id}", response_model=DocumentDetailResponse)
def patch_document_metadata(
    body: DocumentMetadataUpdateRequest,
    document_id: uuid.UUID = Path(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    audit: UploadAuditHook = Depends(get_document_audit),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> DocumentDetailResponse:
    """Partial metadata update for owner or active EDIT grantee.

    Only title, category, and description are accepted. Ownership, storage key,
    size, checksum, MIME type, and deletion state cannot be changed here.
    """
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    fields = body.model_dump(exclude_unset=True)
    try:
        result = update_document_metadata(
            session,
            actor=current_user,
            document_id=document_id,
            fields=fields,
        )
    except DocumentAuthorizationError as exc:
        audit.record(
            action="DOCUMENT_METADATA_UPDATE",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document_id,
            request_id=request_id,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    except DocumentMetadataError as exc:
        audit.record(
            action="DOCUMENT_METADATA_UPDATE",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document_id,
            request_id=request_id,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    reason = "NO_CHANGES" if not result.changed_fields else None
    try:
        audit.record(
            action="DOCUMENT_METADATA_UPDATE",
            outcome="SUCCESS",
            reason_code=reason,
            actor_id=current_user.id,
            document_id=result.document.id,
            request_id=request_id,
            changed_fields=result.changed_fields,
        )
    except Exception as exc:
        logger.exception("Audit failed after metadata update")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Metadata update could not be audited",
        ) from exc

    # Successful PATCH implies OWNER or EDIT (authorization already enforced).
    your_access = (
        "OWNER" if result.document.owner_id == current_user.id else "EDIT"
    )
    document = session.scalars(
        select(Document)
        .options(joinedload(Document.owner))
        .where(Document.id == result.document.id)
    ).unique().one()
    return _detail_response(document, your_access=your_access)


@router.put("/{document_id}/content", response_model=DocumentDetailResponse)
def put_document_content(
    body: DocumentContentUpdateRequest,
    document_id: uuid.UUID = Path(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    storage: R2StorageService = Depends(get_storage),
    audit: UploadAuditHook = Depends(get_document_audit),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> DocumentDetailResponse:
    """Replace DOCX body text for the owner or an active EDIT grantee.

    READ grantees receive 403. Rebuilds a DOCX in private R2 under the existing
    opaque key and updates size/checksum. Does not change ownership or grants.
    """
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    try:
        result = replace_document_text_content(
            session,
            actor=current_user,
            document_id=document_id,
            text=body.text,
            storage=storage,
        )
    except DocumentAuthorizationError as exc:
        audit.record(
            action="DOCUMENT_CONTENT_UPDATE",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document_id,
            request_id=request_id,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    except DocumentContentError as exc:
        audit.record(
            action="DOCUMENT_CONTENT_UPDATE",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document_id,
            request_id=request_id,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    try:
        audit.record(
            action="DOCUMENT_CONTENT_UPDATE",
            outcome="SUCCESS",
            reason_code=None,
            actor_id=current_user.id,
            document_id=result.document.id,
            request_id=request_id,
        )
    except Exception as exc:
        logger.exception("Audit failed after content update")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Content update could not be audited",
        ) from exc

    document = session.scalars(
        select(Document)
        .options(joinedload(Document.owner))
        .where(Document.id == result.document.id)
    ).unique().one()
    return _detail_response(document, your_access=result.your_access)


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
def delete_document(
    document_id: uuid.UUID = Path(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    storage: R2StorageService = Depends(get_storage),
    audit: UploadAuditHook = Depends(get_document_audit),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> DocumentDeleteResponse:
    """Owner-only soft-delete, then best-effort private R2 object removal.

    Soft-delete is applied first so the document is immediately unlistable and
    undownloadable. Success is returned only when storage cleanup completes or
    the object is already absent. Storage cleanup failure leaves the soft-delete
    in place and returns 503 (not a false complete success).
    """
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    try:
        result = soft_delete_document(
            session,
            actor=current_user,
            document_id=document_id,
            storage=storage,
        )
    except DocumentAuthorizationError as exc:
        audit.record(
            action="DOCUMENT_DELETE",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document_id,
            request_id=request_id,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    except DocumentDeletionError as exc:
        audit.record(
            action="DOCUMENT_DELETE",
            outcome="FAILURE",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document_id,
            request_id=request_id,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    assert result.document.deleted_at is not None
    try:
        audit.record(
            action="DOCUMENT_DELETE",
            outcome="SUCCESS",
            reason_code=None,
            actor_id=current_user.id,
            document_id=result.document.id,
            request_id=request_id,
        )
    except Exception as exc:
        # Tombstone + R2 cleanup already applied; do not revive the document.
        # Commit before raising: get_db rolls back on HTTPException.
        logger.exception("Audit failed after document delete")
        try:
            session.commit()
        except Exception:
            logger.exception("Failed to commit soft-delete after audit failure")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document deleted but audit failed",
        ) from exc

    return DocumentDeleteResponse(
        id=result.document.id,
        deleted_at=result.document.deleted_at,
        storage_cleanup=result.storage_cleanup,
    )


@router.get("/{document_id}/download")
def download_document(
    document_id: uuid.UUID = Path(...),
    disposition: Literal["attachment", "inline"] = Query(
        default="attachment",
        description="attachment saves the file; inline is for authenticated content preview",
    ),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    storage: R2StorageService = Depends(get_storage),
    audit: UploadAuditHook = Depends(get_document_audit),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> StreamingResponse:
    """Stream original file bytes from private R2 only after authorization succeeds.

    Never issues public or presigned URLs. Object key is taken from PostgreSQL
    only. Each request re-checks current ownership/grants (immediate revocation).
    Bytes are streamed unchanged — no text/JSON/Base64 conversion.
    """
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())

    try:
        document = require_document_read(
            session,
            user=current_user,
            document_id=document_id,
        )
    except DocumentAuthorizationError as exc:
        audit.record(
            action="DOCUMENT_DOWNLOAD",
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document_id,
            request_id=request_id,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None

    # Authorization succeeded. Only now touch storage. Fail closed if open fails
    # before any document bytes are returned to the client.
    try:
        byte_iter = open_download_stream(storage, document)
        first_chunk = next(byte_iter, None)
    except (DownloadStorageError, StorageError) as exc:
        reason = (
            exc.reason_code
            if isinstance(exc, DownloadStorageError)
            else "STORAGE_DOWNLOAD_FAILED"
        )
        audit.record(
            action="DOCUMENT_DOWNLOAD",
            outcome="FAILURE",
            reason_code=reason,
            actor_id=current_user.id,
            document_id=document.id,
            request_id=request_id,
        )
        logger.warning(
            "Authorized download failed at storage layer",
            extra={"audit_reason": reason, "audit_persisted": False},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document storage is unavailable",
        ) from None

    filename = safe_download_filename(document)
    content_type = document.mime_type or "application/octet-stream"
    # Inline is only meaningful for types the browser can render; always safe.
    content_disposition = (
        f'inline; filename="{filename}"'
        if disposition == "inline"
        else f'attachment; filename="{filename}"'
    )

    def stream_body() -> Iterator[bytes]:
        try:
            if first_chunk is not None:
                yield first_chunk
            yield from byte_iter
        finally:
            close = getattr(byte_iter, "close", None)
            if callable(close):
                close()

    audit.record(
        action="DOCUMENT_DOWNLOAD",
        outcome="SUCCESS",
        reason_code=None,
        actor_id=current_user.id,
        document_id=document.id,
        request_id=request_id,
    )

    headers = {
        "Content-Disposition": content_disposition,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "X-Request-ID": request_id,
    }
    if document.file_size >= 0:
        headers["Content-Length"] = str(document.file_size)

    return StreamingResponse(
        stream_body(),
        media_type=content_type,
        headers=headers,
    )
