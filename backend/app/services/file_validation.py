"""Upload file validation for TrustVault.

Allowed types use magic-byte / structure checks in addition to extension.
This is not malware scanning and does not prove a file is safe to open.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MiB

ALLOWED_EXTENSIONS = frozenset({".pdf", ".docx", ".png", ".jpg", ".jpeg"})

MEDIA_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
PDF_SIGNATURE = b"%PDF-"
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
            "Filename with a supported extension is required",
            reason_code="MISSING_FILENAME",
        )
    # Use only the final suffix; ignore client path segments.
    name = Path(filename.replace("\\", "/").split("/")[-1]).name
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            "Unsupported file type",
            status_code=415,
            reason_code="UNSUPPORTED_EXTENSION",
        )
    return ext


def _is_pdf(data: bytes) -> bool:
    return data.startswith(PDF_SIGNATURE)


def _is_png(data: bytes) -> bool:
    return data.startswith(PNG_SIGNATURE)


def _is_jpeg(data: bytes) -> bool:
    return data.startswith(JPEG_SIGNATURE)


def _is_docx(data: bytes) -> bool:
    if not data.startswith(ZIP_SIGNATURE):
        return False
    try:
        from io import BytesIO

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
    if extension == ".pdf":
        if not _is_pdf(data):
            raise FileValidationError(
                "File content is not a valid PDF",
                status_code=415,
                reason_code="INVALID_PDF_CONTENT",
            )
        return MEDIA_BY_EXTENSION[".pdf"]
    if extension == ".png":
        if not _is_png(data):
            raise FileValidationError(
                "File content is not a valid PNG",
                status_code=415,
                reason_code="INVALID_PNG_CONTENT",
            )
        return MEDIA_BY_EXTENSION[".png"]
    if extension in {".jpg", ".jpeg"}:
        if not _is_jpeg(data):
            raise FileValidationError(
                "File content is not a valid JPEG",
                status_code=415,
                reason_code="INVALID_JPEG_CONTENT",
            )
        return MEDIA_BY_EXTENSION[".jpg"]
    if extension == ".docx":
        if not _is_docx(data):
            raise FileValidationError(
                "File content is not a valid DOCX",
                status_code=415,
                reason_code="INVALID_DOCX_CONTENT",
            )
        return MEDIA_BY_EXTENSION[".docx"]
    raise FileValidationError(
        "Unsupported file type",
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
    expected = expected_media_type.lower()
    jpeg_aliases = {"image/jpeg", "image/jpg"}
    if expected == "image/jpeg":
        if provided not in jpeg_aliases:
            raise FileValidationError(
                "Declared content type does not match file contents",
                status_code=415,
                reason_code="CONTENT_TYPE_MISMATCH",
            )
        return
    if provided != expected:
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
