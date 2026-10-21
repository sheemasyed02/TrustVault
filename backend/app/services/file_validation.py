"""Upload file validation for TrustVault.

TrustVault is a confidential *document* sharing system. Only Microsoft Word
DOCX uploads are accepted so owners and EDIT grantees work with editable
office documents (view/edit locally after authorized download; metadata edits
in-app). PDF/PNG/JPEG are rejected at upload.

Allowed types use structure checks in addition to extension.
This is not malware scanning and does not prove a file is safe to open.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MiB

ALLOWED_EXTENSIONS = frozenset({".docx"})

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

MEDIA_BY_EXTENSION = {
    ".docx": DOCX_MEDIA_TYPE,
}

ZIP_SIGNATURE = b"PK\x03\x04"


class FileValidationError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    extension: str
    media_type: str
    size_bytes: int
    sha256_hex: str
    original_filename: str | None


def normalize_extension(filename: str | None) -> str:
    if not filename or not filename.strip():
        raise FileValidationError(
            "Filename with a .docx extension is required",
            reason_code="MISSING_FILENAME",
        )
    # Use only the final suffix; ignore client path segments.
    name = Path(filename.replace("\\", "/").split("/")[-1]).name
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            "Only DOCX documents are supported",
            status_code=415,
            reason_code="UNSUPPORTED_EXTENSION",
        )
    return ext


def _is_docx(data: bytes) -> bool:
    if not data.startswith(ZIP_SIGNATURE):
        return False
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = set(archive.namelist())
            # Reject path traversal style members.
            for name in names:
                if name.startswith("/") or ".." in Path(name).parts:
                    return False
            if "[Content_Types].xml" not in names:
                return False
            if "word/document.xml" not in names:
                return False
            # Ensure we can read the core document part without extracting to disk.
            with archive.open("word/document.xml") as part:
                head = part.read(256)
                if not head:
                    return False
    except (zipfile.BadZipFile, KeyError, OSError):
        return False
    return True


def detect_media_type(data: bytes, extension: str) -> str:
    if extension == ".docx":
        if not _is_docx(data):
            raise FileValidationError(
                "File content is not a valid DOCX",
                status_code=415,
                reason_code="INVALID_DOCX_CONTENT",
            )
        return MEDIA_BY_EXTENSION[".docx"]
    raise FileValidationError(
        "Only DOCX documents are supported",
        status_code=415,
        reason_code="UNSUPPORTED_EXTENSION",
    )


def validate_client_content_type(
    client_content_type: str | None,
    expected_media_type: str,
) -> None:
    """Reject clearly spoofed Content-Type when the client sends one."""
    if not client_content_type:
        return
    provided = client_content_type.split(";")[0].strip().lower()
    if not provided or provided == "application/octet-stream":
        return
    if provided != expected_media_type.lower():
        raise FileValidationError(
            "Declared content type does not match file contents",
            status_code=415,
            reason_code="CONTENT_TYPE_MISMATCH",
        )


def validate_upload_bytes(
    data: bytes,
    *,
    filename: str | None,
    client_content_type: str | None,
    sha256_hex: str,
) -> ValidatedUpload:
    if not data:
        raise FileValidationError(
            "Empty files are not allowed",
            reason_code="EMPTY_FILE",
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise FileValidationError(
            "File exceeds the 10 MiB size limit",
            status_code=413,
            reason_code="FILE_TOO_LARGE",
        )
    extension = normalize_extension(filename)
    media_type = detect_media_type(data, extension)
    validate_client_content_type(client_content_type, media_type)
    safe_name = Path((filename or "upload").replace("\\", "/").split("/")[-1]).name
    return ValidatedUpload(
        extension=extension,
        media_type=media_type,
        size_bytes=len(data),
        sha256_hex=sha256_hex,
        original_filename=safe_name,
    )
