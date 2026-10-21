"""Authorized private R2 download helpers."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from app.db.models import Document
from app.storage import R2StorageService, StorageError

_CHUNK_SIZE = 1024 * 1024

_MIME_EXTENSIONS = {
    # Primary upload type. Legacy PDF/image keys kept so older stored objects
    # still download with a sensible extension if present in the database.
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}


class DownloadStorageError(Exception):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.reason_code = reason_code


def safe_download_filename(document: Document) -> str:
    """Build a Content-Disposition filename without CR/LF or quote injection."""
    raw = (document.original_filename or document.title or "document").strip()
    # Drop any client path segments; keep only the final name component.
    raw = Path(raw.replace("\\", "/").split("/")[-1]).name
    # Neutralize header-injection vectors before any other rewriting.
    base = raw.replace("\r", " ").replace("\n", " ").replace('"', "")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    base = re.sub(r"_+", "_", base).strip("._") or "document"
    base = base[:200]
    ext = _MIME_EXTENSIONS.get(document.mime_type, "")
    if ext and not base.lower().endswith(ext):
        base = f"{base}{ext}"
    return base


def open_download_stream(
    storage: R2StorageService,
    document: Document,
    *,
    chunk_size: int = _CHUNK_SIZE,
) -> Iterator[bytes]:
    """Stream object bytes after authz; always close the R2 body when finished."""
    try:
        with storage.open_object(document.storage_key) as body:
            while True:
                chunk = body.read(chunk_size)
                if not chunk:
                    break
                yield chunk
    except StorageError as exc:
        raise DownloadStorageError(
            "Document storage is unavailable",
            reason_code="STORAGE_DOWNLOAD_FAILED",
        ) from exc
