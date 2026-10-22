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
    require_document_owner,
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
from app.schemas.audit import (
    AuditEventListResponse,
    DocumentViewActivityListResponse,
)
from app.services.audit_trail import (
    enrich_audit_event_responses,
    list_audit_events,
    summarize_document_audit,
)
from app.services.document_view_audit import (
    list_owner_document_view_activity,
    recent_successful_view_exists,
    view_event_metadata,
)
from app.services.docx_to_pdf import (
    DocxConversionError,
    convert_docx_bytes_to_pdf_detailed,
)
from app.services.document_download import (
    DownloadStorageError,
    open_download_stream,
    read_object_bytes,
    safe_download_filename,
    safe_pdf_download_filename,
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
from app.services.file_validation import (
    DOCX_MEDIA_TYPE,
    MAX_UPLOAD_BYTES,
    PDF_MEDIA_TYPE,
)
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


@router.get("/view-activity", response_model=DocumentViewActivityListResponse)
def owner_document_view_activity(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> DocumentViewActivityListResponse:
    """Owner-only per-document authorised view counts (not proof of reading).

    Platform VIEWER/ADMIN without ownership see an empty set via ownership filter
    (ADMIN alone never expands owned documents). Counts come from persisted
    ``DOCUMENT_VIEW`` SUCCESS audit rows only.
    """
    if current_user.role != "OWNER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only document owners can inspect view activity summaries",
        )
    return list_owner_document_view_activity(
        session,
        owner=current_user,
        page=page,
        page_size=page_size,
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
    """Partial metadata update for the document owner only.

    EDIT grantees may change file content via PUT /content but cannot change
    title, category, or description through this endpoint.

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

    # Successful PATCH implies document ownership (authorization already enforced).
    your_access = "OWNER"
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

    READ grantees receive 403. PDF content editing is not supported (415).
    Rewrites ``word/document.xml`` while preserving other DOCX package parts
    when possible. Does not change metadata, ownership, or grants. Audited as
    DOCUMENT_CONTENT_UPDATE.
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
        # Durable chain only accepts SUCCESS|DENIED — record storage failures as DENIED.
        audit.record(
            action="DOCUMENT_DELETE",
            outcome="DENIED",
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


@router.get("/{document_id}/audit", response_model=AuditEventListResponse)
def list_document_audit_events(
    document_id: uuid.UUID = Path(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    action: str | None = Query(
        default=None,
        description="Optional action filter, e.g. DOCUMENT_VIEW",
    ),
    focus: str | None = Query(
        default=None,
        description=(
            "Optional focus: external_views | owner_views | downloads | denied | all. "
            "external_views excludes the owner's own DOCUMENT_VIEW SUCCESS events."
        ),
    ),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> AuditEventListResponse:
    """Owner-only activity log and summary for one owned document.

    Non-owners (including other document owners guessing IDs) are denied.
    Never returns file bytes or storage keys. A successful DOCUMENT_VIEW proves
    an authorised preview request, not that a person read or understood the file.
    Owner self-views remain in the trail; ``focus=external_views`` and summary
    ``external_*`` fields exclude them from dashboard-style counts.
    """
    try:
        document = require_document_owner(
            session,
            user=current_user,
            document_id=document_id,
        )
    except DocumentAuthorizationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None

    focus_norm = (focus or "").strip().lower() or None
    list_action = action
    list_outcome: str | None = None
    list_actor_id = None
    list_exclude_actor_id = None
    if focus_norm == "external_views":
        list_action = "DOCUMENT_VIEW"
        list_outcome = "SUCCESS"
        list_exclude_actor_id = document.owner_id
    elif focus_norm == "owner_views":
        list_action = "DOCUMENT_VIEW"
        list_actor_id = document.owner_id
    elif focus_norm == "downloads":
        list_action = "DOCUMENT_DOWNLOAD"
    elif focus_norm == "denied":
        list_outcome = "DENIED"
    elif focus_norm not in {None, "all"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="focus must be external_views, owner_views, downloads, denied, or all",
        )

    result = list_audit_events(
        session,
        page=page,
        page_size=page_size,
        document_id=document_id,
        action=list_action,
        outcome=list_outcome,
        actor_id=list_actor_id,
        exclude_actor_id=list_exclude_actor_id,
    )
    return AuditEventListResponse(
        results=enrich_audit_event_responses(session, result.items),
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        total_pages=result.total_pages,
        summary=summarize_document_audit(
            session,
            document_id=document_id,
            owner_id=document.owner_id,
        ),
    )


@router.get("/{document_id}/download")
def download_document(
    document_id: uuid.UUID = Path(...),
    disposition: Literal["attachment", "inline"] = Query(
        default="attachment",
        description=(
            "attachment returns a PDF (DOCX is converted from the latest saved "
            "bytes; legacy PDF rows are streamed as-is). "
            "inline returns original bytes for authenticated in-app preview."
        ),
    ),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    storage: R2StorageService = Depends(get_storage),
    audit: UploadAuditHook = Depends(get_document_audit),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> StreamingResponse:
    """Stream document bytes from private R2 only after authorization succeeds.

    Never issues public or presigned URLs. Object key is taken from PostgreSQL
    only. Each request re-checks current ownership/grants (immediate revocation).

    Downloads (attachment) always deliver PDF. New uploads are DOCX-only and are
    converted to PDF from the current private object. Legacy PDF rows (if any)
    are streamed unchanged. Inline preview keeps the original stored format.
    """
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    # Inline = authorised preview (DOCUMENT_VIEW). Attachment = download (DOCUMENT_DOWNLOAD).
    # Metadata/list GETs never hit this route and therefore never inflate view counts.
    is_view = disposition == "inline"
    audit_action = "DOCUMENT_VIEW" if is_view else "DOCUMENT_DOWNLOAD"
    audit_meta = (
        view_event_metadata(actor=current_user, disposition=disposition)
        if is_view
        else {"disposition": disposition}
    )

    try:
        document = require_document_read(
            session,
            user=current_user,
            document_id=document_id,
        )
    except DocumentAuthorizationError as exc:
        audit.record(
            action=audit_action,
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document_id,
            request_id=request_id,
            metadata=audit_meta,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None

    as_pdf_download = disposition == "attachment"
    payload: bytes | None = None
    content_type: str
    filename: str
    byte_iter: Iterator[bytes] | None = None
    first_chunk: bytes | None = None
    conversion_method: str | None = None

    try:
        if as_pdf_download and document.mime_type == DOCX_MEDIA_TYPE:
            raw = read_object_bytes(storage, document)
            converted = convert_docx_bytes_to_pdf_detailed(raw)
            payload = converted.pdf_bytes
            conversion_method = converted.method
            content_type = PDF_MEDIA_TYPE
            filename = safe_pdf_download_filename(document)
        elif as_pdf_download and document.mime_type == PDF_MEDIA_TYPE:
            byte_iter = open_download_stream(storage, document)
            first_chunk = next(byte_iter, None)
            # Validate native PDF downloads still look like PDFs.
            if first_chunk is not None and not first_chunk.startswith(b"%PDF"):
                audit.record(
                    action=audit_action,
                    outcome="DENIED",
                    reason_code="INVALID_STORED_PDF",
                    actor_id=current_user.id,
                    document_id=document.id,
                    request_id=request_id,
                    metadata=audit_meta,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Stored PDF is invalid",
                )
            content_type = PDF_MEDIA_TYPE
            filename = safe_pdf_download_filename(document)
        else:
            # Inline preview (or legacy types): original stored bytes.
            byte_iter = open_download_stream(storage, document)
            first_chunk = next(byte_iter, None)
            content_type = document.mime_type or "application/octet-stream"
            filename = safe_download_filename(document)
    except DocxConversionError as exc:
        audit.record(
            action=audit_action,
            outcome="DENIED",
            reason_code=exc.reason_code,
            actor_id=current_user.id,
            document_id=document.id,
            request_id=request_id,
            metadata=audit_meta,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document could not be converted to PDF",
        ) from None
    except (DownloadStorageError, StorageError) as exc:
        reason = (
            exc.reason_code
            if isinstance(exc, DownloadStorageError)
            else "STORAGE_DOWNLOAD_FAILED"
        )
        audit.record(
            action=audit_action,
            outcome="DENIED",
            reason_code=reason,
            actor_id=current_user.id,
            document_id=document.id,
            request_id=request_id,
            metadata=audit_meta,
        )
        logger.warning(
            "Authorized download failed at storage layer",
            extra={"audit_reason": reason},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document storage is unavailable",
        ) from None

    content_disposition = (
        f'inline; filename="{filename}"'
        if disposition == "inline"
        else f'attachment; filename="{filename}"'
    )

    def stream_body() -> Iterator[bytes]:
        if payload is not None:
            yield payload
            return
        assert byte_iter is not None
        try:
            if first_chunk is not None:
                yield first_chunk
            yield from byte_iter
        finally:
            close = getattr(byte_iter, "close", None)
            if callable(close):
                close()

    success_reason: str | None = None
    if as_pdf_download and document.mime_type == DOCX_MEDIA_TYPE:
        success_reason = (
            "PDF_CONVERTED_LIBREOFFICE"
            if conversion_method == "libreoffice"
            else "PDF_CONVERTED_FALLBACK"
        )
    # Dedupe rapid repeat inline previews (e.g. React remount) so one user action
    # does not inflate authorised view counts. Downloads are always recorded.
    should_record_success = True
    if is_view and recent_successful_view_exists(
        session,
        document_id=document.id,
        actor_id=current_user.id,
    ):
        should_record_success = False
    if should_record_success:
        audit.record(
            action=audit_action,
            outcome="SUCCESS",
            reason_code=success_reason,
            actor_id=current_user.id,
            document_id=document.id,
            request_id=request_id,
            metadata=audit_meta,
        )

    headers = {
        "Content-Disposition": content_disposition,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "X-Request-ID": request_id,
    }
    if payload is not None:
        headers["Content-Length"] = str(len(payload))
    elif document.file_size >= 0 and document.mime_type == PDF_MEDIA_TYPE:
        headers["Content-Length"] = str(document.file_size)

    return StreamingResponse(
        stream_body(),
        media_type=content_type,
        headers=headers,
    )
