"""Replace DOCX document body after EDIT authorization.

Owners and active EDIT grantees may replace the stored Word document with a
new DOCX built from plain text. Complex Word formatting is not preserved —
this supports in-app view/edit for TrustVault's confidential document workflow.
"""

from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from xml.sax.saxutils import escape

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Document, User
from app.services.document_authorization import (
    DocumentAuthorizationError,
    require_document_edit_context,
)
from app.services.file_validation import DOCX_MEDIA_TYPE, MAX_UPLOAD_BYTES
from app.storage import R2StorageService, StorageError
from app.storage.hashing import sha256_hex_bytes

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 500_000


class DocumentContentError(Exception):
    def __init__(self, message: str, *, status_code: int, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class ContentReplaceResult:
    document: Document
    your_access: str


def build_docx_bytes_from_text(text: str) -> bytes:
    """Build a minimal valid DOCX from plain text (paragraphs by newline)."""
    paragraphs = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not paragraphs:
        paragraphs = [""]

    body_parts: list[str] = []
    for line in paragraphs:
        body_parts.append(
            "<w:p><w:r><w:t xml:space=\"preserve\">"
            f"{escape(line)}"
            "</w:t></w:r></w:p>"
        )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body_parts)}</w:body>"
        "</w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def replace_document_text_content(
    session: Session,
    *,
    actor: User,
    document_id,
    text: str,
    storage: R2StorageService,
) -> ContentReplaceResult:
    """Authorize EDIT, write a new DOCX to the existing private key, update metadata."""
    if text is None:
        raise DocumentContentError(
            "Document text is required",
            status_code=422,
            reason_code="CONTENT_REQUIRED",
        )
    if len(text) > MAX_CONTENT_CHARS:
        raise DocumentContentError(
            "Document text is too long",
            status_code=422,
            reason_code="CONTENT_TOO_LONG",
        )

    try:
        context = require_document_edit_context(
            session,
            user=actor,
            document_id=document_id,
        )
    except DocumentAuthorizationError:
        raise

    document = context.document
    if document.mime_type != DOCX_MEDIA_TYPE:
        raise DocumentContentError(
            "Only DOCX documents can be edited in TrustVault",
            status_code=415,
            reason_code="UNSUPPORTED_CONTENT_TYPE",
        )

    file_bytes = build_docx_bytes_from_text(text)
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise DocumentContentError(
            "Updated document exceeds the 10 MiB size limit",
            status_code=413,
            reason_code="FILE_TOO_LARGE",
        )

    digest = sha256_hex_bytes(file_bytes)
    try:
        storage.upload_bytes(
            document.storage_key,
            file_bytes,
            content_type=DOCX_MEDIA_TYPE,
            expected_sha256=digest,
        )
    except StorageError:
        logger.error(
            "Document content storage replace failed",
            extra={"upload_stage": "r2_put_replace"},
        )
        raise DocumentContentError(
            "Document storage update failed",
            status_code=503,
            reason_code="STORAGE_REPLACE_FAILED",
        ) from None

    document.file_size = len(file_bytes)
    document.sha256_checksum = digest
    document.mime_type = DOCX_MEDIA_TYPE
    document.updated_at = datetime.now(timezone.utc)

    try:
        session.flush()
    except SQLAlchemyError:
        logger.error("Document content DB update failed after storage put")
        raise DocumentContentError(
            "Document persistence failed after storage update",
            status_code=503,
            reason_code="DB_UPDATE_FAILED",
        ) from None

    from app.services.document_authorization import caller_access_level

    return ContentReplaceResult(
        document=document,
        your_access=caller_access_level(context),
    )
