"""Private Cloudflare R2 storage helpers (S3-compatible API)."""

from app.storage.exceptions import (
    StorageConfigurationError,
    StorageError,
    StorageIntegrityError,
    StorageNotFoundError,
    StorageOperationError,
)
from app.storage.keys import generate_object_key
from app.storage.r2 import ObjectMetadata, R2StorageService, UploadResult, get_storage_service

__all__ = [
    "ObjectMetadata",
    "R2StorageService",
    "StorageConfigurationError",
    "StorageError",
    "StorageIntegrityError",
    "StorageNotFoundError",
    "StorageOperationError",
    "UploadResult",
    "generate_object_key",
    "get_storage_service",
]
