"""Private Cloudflare R2 storage service (S3-compatible, no public URLs)."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, BinaryIO, Generator, Iterator

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings, get_settings
from app.storage.config import R2Config, load_r2_config
from app.storage.exceptions import (
    StorageIntegrityError,
    StorageNotFoundError,
    StorageOperationError,
)
from app.storage.hashing import sha256_hex_bytes, sha256_hex_stream

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UploadResult:
    storage_key: str
    size_bytes: int
    sha256_hex: str
    content_type: str | None
    checksum_verified: bool


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    storage_key: str
    content_length: int | None
    content_type: str | None
    etag: str | None


class R2StorageService:
    """Upload/download/delete private objects through the backend only."""

    def __init__(
        self,
        config: R2Config,
        *,
        client: BaseClient | None = None,
    ) -> None:
        self._config = config
        self._client = client or self._build_client(config)

    @staticmethod
    def _build_client(config: R2Config) -> BaseClient:
        # region_name "auto" is the Cloudflare R2 convention for S3 clients.
        return boto3.client(
            "s3",
            endpoint_url=config.endpoint_url,
            aws_access_key_id=config.access_key_id,
            aws_secret_access_key=config.secret_access_key,
            region_name="auto",
        )

    @property
    def bucket_name(self) -> str:
        return self._config.bucket_name

    @property
    def endpoint_url(self) -> str:
        return self._config.endpoint_url

    def upload_bytes(
        self,
        storage_key: str,
        data: bytes,
        *,
        content_type: str | None = None,
        expected_sha256: str | None = None,
    ) -> UploadResult:
        key = self._require_key(storage_key)
        digest = sha256_hex_bytes(data)
        verified = self._maybe_verify_checksum(digest, expected_sha256)
        extra_args: dict[str, str] = {}
        if content_type:
            extra_args["ContentType"] = content_type

        try:
            self._client.put_object(
                Bucket=self._config.bucket_name,
                Key=key,
                Body=data,
                **extra_args,
            )
        except (ClientError, BotoCoreError) as exc:
            raise self._map_error(exc, operation="upload") from None

        logger.info(
            "R2 upload completed",
            extra={
                "storage_operation": "upload",
                "object_size": len(data),
                "checksum_verified": verified,
            },
        )
        return UploadResult(
            storage_key=key,
            size_bytes=len(data),
            sha256_hex=digest,
            content_type=content_type,
            checksum_verified=verified,
        )

    def upload_fileobj(
        self,
        storage_key: str,
        fileobj: BinaryIO,
        *,
        content_type: str | None = None,
        expected_sha256: str | None = None,
    ) -> UploadResult:
        key = self._require_key(storage_key)
        digest, size = sha256_hex_stream(fileobj)
        verified = self._maybe_verify_checksum(digest, expected_sha256)
        extra_args: dict[str, str] = {}
        if content_type:
            extra_args["ContentType"] = content_type

        try:
            if fileobj.seekable():
                fileobj.seek(0)
            upload_kwargs: dict[str, Any] = {}
            if extra_args:
                upload_kwargs["ExtraArgs"] = extra_args
            self._client.upload_fileobj(
                fileobj,
                self._config.bucket_name,
                key,
                **upload_kwargs,
            )
        except (ClientError, BotoCoreError) as exc:
            raise self._map_error(exc, operation="upload") from None

        logger.info(
            "R2 stream upload completed",
            extra={
                "storage_operation": "upload_stream",
                "object_size": size,
                "checksum_verified": verified,
            },
        )
        return UploadResult(
            storage_key=key,
            size_bytes=size,
            sha256_hex=digest,
            content_type=content_type,
            checksum_verified=verified,
        )

    @contextmanager
    def open_object(self, storage_key: str) -> Generator[BinaryIO, None, None]:
        """Yield a readable body stream for a private object."""
        key = self._require_key(storage_key)
        try:
            response = self._client.get_object(
                Bucket=self._config.bucket_name,
                Key=key,
            )
        except (ClientError, BotoCoreError) as exc:
            raise self._map_error(exc, operation="download") from None

        body = response["Body"]
        try:
            yield body
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()

    def iter_object_chunks(
        self,
        storage_key: str,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> Iterator[bytes]:
        """Iterate object bytes without exposing a public download URL."""
        with self.open_object(storage_key) as body:
            while True:
                chunk = body.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    def delete_object(self, storage_key: str) -> None:
        key = self._require_key(storage_key)
        try:
            self._client.delete_object(
                Bucket=self._config.bucket_name,
                Key=key,
            )
        except (ClientError, BotoCoreError) as exc:
            raise self._map_error(exc, operation="delete") from None

        logger.info(
            "R2 delete completed",
            extra={"storage_operation": "delete"},
        )

    def object_exists(self, storage_key: str) -> bool:
        key = self._require_key(storage_key)
        try:
            self._client.head_object(
                Bucket=self._config.bucket_name,
                Key=key,
            )
            return True
        except ClientError as exc:
            if self._is_not_found(exc):
                return False
            raise self._map_error(exc, operation="head") from None
        except BotoCoreError as exc:
            raise self._map_error(exc, operation="head") from None

    def get_object_metadata(self, storage_key: str) -> ObjectMetadata:
        key = self._require_key(storage_key)
        try:
            response = self._client.head_object(
                Bucket=self._config.bucket_name,
                Key=key,
            )
        except (ClientError, BotoCoreError) as exc:
            raise self._map_error(exc, operation="head") from None

        return ObjectMetadata(
            storage_key=key,
            content_length=response.get("ContentLength"),
            content_type=response.get("ContentType"),
            etag=response.get("ETag"),
        )

    @staticmethod
    def _require_key(storage_key: str) -> str:
        key = (storage_key or "").strip()
        if not key:
            raise StorageOperationError("Storage key is required")
        if key.startswith("/") or ".." in key.split("/"):
            raise StorageOperationError("Invalid storage key")
        return key

    @staticmethod
    def _maybe_verify_checksum(actual: str, expected: str | None) -> bool:
        if expected is None:
            return False
        if expected.lower() != actual.lower():
            raise StorageIntegrityError("Object checksum mismatch")
        return True

    @staticmethod
    def _is_not_found(exc: ClientError) -> bool:
        code = exc.response.get("Error", {}).get("Code", "")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return code in {"404", "NoSuchKey", "NotFound"} or status == 404

    def _map_error(self, exc: Exception, *, operation: str) -> StorageError:
        if isinstance(exc, ClientError) and self._is_not_found(exc):
            return StorageNotFoundError("Object not found")

        # Log only a safe operation label — never credentials, bodies, or SDK dumps.
        logger.error(
            "R2 storage operation failed",
            extra={"storage_operation": operation},
        )
        return StorageOperationError("Storage operation failed")


def get_storage_service(settings: Settings | None = None) -> R2StorageService:
    """Build a storage service from environment configuration."""
    config = load_r2_config(settings or get_settings())
    return R2StorageService(config)
