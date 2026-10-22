"""Replace DOCX document body after EDIT_CONTENT authorization.

Owners and active EDIT grantees may update the stored Word document body text.
When the existing private object is a valid DOCX package, non-body package parts
(styles, media, headers, footers, relationships) are preserved. The body itself
is rewritten as plain paragraphs from the editor text — tables, images, and
inline drawings that lived inside ``word/document.xml`` are not reconstructed.

PDF in-app content editing is **not** supported for any legacy PDF rows.
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
    require_document_content_edit_context,
)
from app.services.file_validation import (
    DOCX_MEDIA_TYPE,
    MAX_UPLOAD_BYTES,
    PDF_MEDIA_TYPE,
)
from app.storage import R2StorageService, StorageError
from app.storage.hashing import sha256_hex_bytes

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 500_000

_DOCX_DOCUMENT_XML_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body>{body}</w:body>"
    "</w:document>"
)

_MINIMAL_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)

_MINIMAL_RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)


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


def _body_xml_from_text(text: str) -> str:
    paragraphs = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not paragraphs:
        paragraphs = [""]
    parts: list[str] = []
    for line in paragraphs:
        parts.append(
            '<w:p><w:r><w:t xml:space="preserve">'
            f"{escape(line)}"
            "</w:t></w:r></w:p>"
        )
    return "".join(parts)


def build_docx_bytes_from_text(text: str) -> bytes:
    """Build a minimal valid DOCX from plain text (used when no prior package exists)."""
    document_xml = _DOCX_DOCUMENT_XML_TEMPLATE.format(body=_body_xml_from_text(text))
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _MINIMAL_CONTENT_TYPES)
        archive.writestr("_rels/.rels", _MINIMAL_RELS)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def rebuild_docx_preserving_package(original_bytes: bytes | None, text: str) -> bytes:
    """Rewrite body text while keeping other DOCX package parts when possible.

    Limitations: body-level tables, images, and drawings in document.xml are
    replaced by plain paragraphs. Package parts outside document.xml (styles,
    theme, headers/footers, embedded media files) are copied through unchanged.
    """
    document_xml = _DOCX_DOCUMENT_XML_TEMPLATE.format(body=_body_xml_from_text(text))
    if not original_bytes or not original_bytes.startswith(b"PK\x03\x04"):
        return build_docx_bytes_from_text(text)

    try:
        with zipfile.ZipFile(BytesIO(original_bytes), "r") as source:
            names = source.namelist()
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                return build_docx_bytes_from_text(text)

            out = BytesIO()
            with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as dest:
                for info in source.infolist():
                    if info.filename == "word/document.xml":
                        dest.writestr(info, document_xml)
                        continue
                    # Skip directory placeholders.
                    if info.is_dir():
                        continue
                    dest.writestr(info, source.read(info.filename))
            return out.getvalue()
    except (zipfile.BadZipFile, KeyError, OSError):
        logger.warning(
            "Could not preserve DOCX package; falling back to minimal rebuild",
            extra={"audit_reason": "DOCX_PACKAGE_PRESERVE_FAILED"},
        )
        return build_docx_bytes_from_text(text)


def _read_existing_object_bytes(
    storage: R2StorageService,
    document: Document,
) -> bytes | None:
    try:
        with storage.open_object(document.storage_key) as stream:
            return stream.read()
    except StorageError:
        logger.warning(
            "Existing DOCX could not be read before content replace; using minimal rebuild",
            extra={"audit_reason": "STORAGE_READ_BEFORE_REPLACE_FAILED"},
        )
        return None
    except OSError:
        return None


def replace_document_text_content(
    session: Session,
    *,
    actor: User,
    document_id,
    text: str,
    storage: R2StorageService,
) -> ContentReplaceResult:
    """Authorize content edit; update DOCX under the existing private key."""
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
        context = require_document_content_edit_context(
            session,
            user=actor,
            document_id=document_id,
        )
    except DocumentAuthorizationError:
        raise

    document = context.document
    if document.mime_type == PDF_MEDIA_TYPE:
        raise DocumentContentError(
            "PDF content editing is not supported. Preview and download are available; "
            "in-app text editing applies to DOCX documents only.",
            status_code=415,
            reason_code="PDF_CONTENT_EDIT_UNSUPPORTED",
        )
    if document.mime_type != DOCX_MEDIA_TYPE:
        raise DocumentContentError(
            "Only DOCX documents can be edited in TrustVault",
            status_code=415,
            reason_code="UNSUPPORTED_CONTENT_TYPE",
        )

    original = _read_existing_object_bytes(storage, document)
    file_bytes = rebuild_docx_preserving_package(original, text)
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
