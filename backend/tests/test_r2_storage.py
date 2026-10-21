"""Unit tests for private R2 storage using a stubbed S3 client."""

from __future__ import annotations

import io
import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.storage import (
    R2StorageService,
    StorageConfigurationError,
    StorageIntegrityError,
    StorageNotFoundError,
    StorageOperationError,
    generate_object_key,
    get_storage_service,
)
from app.storage.config import load_r2_config, r2_config_presence


def _settings(**overrides: Any) -> Settings:
    base = {
        "DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/trustvault_db",
        "R2_ACCOUNT_ID": "acct123",
        "R2_ACCESS_KEY_ID": "AKIA_TEST_KEY",
        "R2_SECRET_ACCESS_KEY": "super-secret-r2-key",
        "R2_BUCKET_NAME": "trustvault-test",
        "R2_ENDPOINT_URL": "https://acct123.r2.cloudflarestorage.com",
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_load_r2_config_from_settings():
    config = load_r2_config(_settings())
    assert config.account_id == "acct123"
    assert config.bucket_name == "trustvault-test"
    assert config.endpoint_url == "https://acct123.r2.cloudflarestorage.com"
    assert config.access_key_id == "AKIA_TEST_KEY"


def test_missing_r2_configuration_fails_safely():
    settings = _settings(
        R2_ACCESS_KEY_ID="",
        R2_SECRET_ACCESS_KEY="",
        R2_BUCKET_NAME="",
    )
    with pytest.raises(StorageConfigurationError, match="Missing:") as exc_info:
        load_r2_config(settings)
    message = str(exc_info.value)
    assert "R2_ACCESS_KEY_ID" in message
    assert "super-secret" not in message
    assert "AKIA_TEST_KEY" not in message


def test_r2_config_presence_reports_names_not_values():
    presence = r2_config_presence(_settings())
    assert presence["R2_ACCOUNT_ID"] is True
    assert presence["R2_SECRET_ACCESS_KEY"] is True
    serialized = str(presence)
    assert "super-secret" not in serialized
    assert "AKIA_TEST_KEY" not in serialized


def test_placeholder_endpoint_rewritten_from_account_id():
    config = load_r2_config(
        _settings(
            R2_ENDPOINT_URL="https://your_account_id.r2.cloudflarestorage.com",
            R2_ACCOUNT_ID="acct999",
        )
    )
    assert config.endpoint_url == "https://acct999.r2.cloudflarestorage.com"


def test_get_storage_service_builds_boto_client_with_endpoint_and_bucket():
    settings = _settings()
    fake_client = MagicMock()

    with patch("app.storage.r2.boto3.client", return_value=fake_client) as client_factory:
        service = get_storage_service(settings)

    client_factory.assert_called_once_with(
        "s3",
        endpoint_url="https://acct123.r2.cloudflarestorage.com",
        aws_access_key_id="AKIA_TEST_KEY",
        aws_secret_access_key="super-secret-r2-key",
        region_name="auto",
    )
    assert service.bucket_name == "trustvault-test"
    assert service.endpoint_url == "https://acct123.r2.cloudflarestorage.com"


def test_upload_bytes_success():
    client = MagicMock()
    service = R2StorageService(load_r2_config(_settings()), client=client)
    payload = b"confidential-bytes"

    result = service.upload_bytes(
        "objects/test-key",
        payload,
        content_type="application/pdf",
    )

    client.put_object.assert_called_once_with(
        Bucket="trustvault-test",
        Key="objects/test-key",
        Body=payload,
        ContentType="application/pdf",
    )
    assert result.storage_key == "objects/test-key"
    assert result.size_bytes == len(payload)
    assert result.sha256_hex
    assert result.checksum_verified is False


def test_upload_bytes_verifies_expected_sha256_when_provided():
    client = MagicMock()
    service = R2StorageService(load_r2_config(_settings()), client=client)
    payload = b"abc"
    # echo -n abc | sha256sum
    expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

    result = service.upload_bytes(
        "objects/verified",
        payload,
        expected_sha256=expected,
    )
    assert result.checksum_verified is True

    with pytest.raises(StorageIntegrityError):
        service.upload_bytes(
            "objects/bad",
            payload,
            expected_sha256="0" * 64,
        )
    assert client.put_object.call_count == 1


def test_upload_fileobj_success():
    client = MagicMock()
    service = R2StorageService(load_r2_config(_settings()), client=client)
    stream = io.BytesIO(b"streamed-document")

    result = service.upload_fileobj(
        "objects/stream-key",
        stream,
        content_type="text/plain",
    )

    client.upload_fileobj.assert_called_once()
    args, kwargs = client.upload_fileobj.call_args
    assert args[1] == "trustvault-test"
    assert args[2] == "objects/stream-key"
    assert kwargs["ExtraArgs"] == {"ContentType": "text/plain"}
    assert result.size_bytes == len(b"streamed-document")
    assert result.checksum_verified is False


def test_open_object_and_iter_chunks_success():
    client = MagicMock()
    body = io.BytesIO(b"hello-world")
    client.get_object.return_value = {"Body": body}
    service = R2StorageService(load_r2_config(_settings()), client=client)

    with service.open_object("objects/read-key") as stream:
        assert stream.read() == b"hello-world"

    client.get_object.assert_called_with(
        Bucket="trustvault-test",
        Key="objects/read-key",
    )

    client.get_object.return_value = {"Body": io.BytesIO(b"abcdef")}
    chunks = list(service.iter_object_chunks("objects/read-key", chunk_size=2))
    assert chunks == [b"ab", b"cd", b"ef"]


def test_delete_object_success():
    client = MagicMock()
    service = R2StorageService(load_r2_config(_settings()), client=client)
    service.delete_object("objects/delete-me")
    client.delete_object.assert_called_once_with(
        Bucket="trustvault-test",
        Key="objects/delete-me",
    )


def test_object_exists_and_metadata():
    client = MagicMock()
    client.head_object.return_value = {
        "ContentLength": 12,
        "ContentType": "application/pdf",
        "ETag": '"abc"',
    }
    service = R2StorageService(load_r2_config(_settings()), client=client)

    assert service.object_exists("objects/meta") is True
    meta = service.get_object_metadata("objects/meta")
    assert meta.content_length == 12
    assert meta.content_type == "application/pdf"
    assert meta.etag == '"abc"'


def test_missing_object_raises_safe_not_found():
    client = MagicMock()
    client.get_object.side_effect = ClientError(
        {
            "Error": {"Code": "NoSuchKey", "Message": "not found"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        },
        "GetObject",
    )
    service = R2StorageService(load_r2_config(_settings()), client=client)

    with pytest.raises(StorageNotFoundError, match="Object not found"):
        with service.open_object("objects/missing"):
            pass


def test_storage_failure_is_safe():
    client = MagicMock()
    client.put_object.side_effect = ClientError(
        {
            "Error": {"Code": "InternalError", "Message": "boom secret=super-secret-r2-key"},
            "ResponseMetadata": {"HTTPStatusCode": 500},
        },
        "PutObject",
    )
    service = R2StorageService(load_r2_config(_settings()), client=client)

    with pytest.raises(StorageOperationError, match="Storage operation failed") as exc_info:
        service.upload_bytes("objects/fail", b"data")
    assert "super-secret-r2-key" not in str(exc_info.value)


def test_no_public_or_presigned_url_helpers():
    service = R2StorageService(load_r2_config(_settings()), client=MagicMock())
    public_names = [
        name
        for name in dir(service)
        if "presign" in name.lower() or "public_url" in name.lower()
    ]
    assert public_names == []
    assert not hasattr(service, "generate_presigned_url")
    assert not hasattr(service, "get_public_url")


def test_generate_object_key_is_opaque():
    key = generate_object_key()
    assert key.startswith("objects/")
    assert ".." not in key
    assert " " not in key
    assert generate_object_key() != key


def test_logs_do_not_include_credentials_or_document_bytes(caplog: pytest.LogCaptureFixture):
    client = MagicMock()
    service = R2StorageService(load_r2_config(_settings()), client=client)
    secret = "super-secret-r2-key"
    document = b"TOP-SECRET-DOCUMENT-CONTENT"

    with caplog.at_level(logging.INFO, logger="app.storage.r2"):
        service.upload_bytes("objects/log-test", document)

    combined = " | ".join(record.getMessage() for record in caplog.records)
    assert secret not in combined
    assert "TOP-SECRET-DOCUMENT-CONTENT" not in combined
    assert document.decode() not in combined
