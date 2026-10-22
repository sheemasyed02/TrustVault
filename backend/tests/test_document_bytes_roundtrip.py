"""Upload → private storage → download/preview byte integrity tests."""

from __future__ import annotations

import contextlib
import hashlib
import io
import uuid
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.documents import get_document_audit, get_storage, get_upload_audit
from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import Document, DocumentPermission, User
from app.db.session import get_db, reset_engine
from app.main import app
from app.services.upload_audit import RecordingUploadAuditHook
from app.storage import StorageNotFoundError, StorageOperationError
from app.storage.hashing import sha256_hex_bytes

TEST_JWT_SECRET = "unit-test-jwt-secret-key-32chars-min"

# Distinct DOCX payload so accidental placeholders cannot pass equality checks.
KNOWN_DOCX = b'PK\x03\x04\x14\x00\x00\x00\x00\x00\xe0\x95U]\xea\xa5\x16\xa8i\x00\x00\x00i\x00\x00\x00\x13\x00\x00\x00[Content_Types].xml<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>PK\x03\x04\x14\x00\x00\x00\x00\x00\xe0\x95U]\xe2\xa3\xb9 \xbe\x00\x00\x00\xbe\x00\x00\x00\x11\x00\x00\x00word/document.xml<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:t>TrustVault-roundtrip-marker-9f3c2a</w:t></w:p></w:body></w:document>PK\x01\x02\x14\x00\x14\x00\x00\x00\x00\x00\xe0\x95U]\xea\xa5\x16\xa8i\x00\x00\x00i\x00\x00\x00\x13\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x80\x01\x00\x00\x00\x00[Content_Types].xmlPK\x01\x02\x14\x00\x14\x00\x00\x00\x00\x00\xe0\x95U]\xe2\xa3\xb9 \xbe\x00\x00\x00\xbe\x00\x00\x00\x11\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x80\x01\x9a\x00\x00\x00word/document.xmlPK\x05\x06\x00\x00\x00\x00\x02\x00\x02\x00\x80\x00\x00\x00\x87\x01\x00\x00\x00\x00'
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class InMemoryR2:
    """Minimal private-object store used only by integrity tests."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str | None]] = {}

    def upload_bytes(
        self,
        storage_key: str,
        data: bytes,
        *,
        content_type: str | None = None,
        expected_sha256: str | None = None,
    ) -> MagicMock:
        if expected_sha256 is not None:
            actual = sha256_hex_bytes(data)
            assert actual == expected_sha256
        self.objects[storage_key] = (bytes(data), content_type)
        result = MagicMock()
        result.storage_key = storage_key
        result.size_bytes = len(data)
        result.sha256_hex = sha256_hex_bytes(data)
        result.content_type = content_type
        result.checksum_verified = expected_sha256 is not None
        return result

    def open_object(self, storage_key: str):
        if storage_key not in self.objects:
            raise StorageNotFoundError("Object not found")
        data, _ = self.objects[storage_key]
        stream = io.BytesIO(data)

        @contextlib.contextmanager
        def _cm():
            try:
                yield stream
            finally:
                stream.close()

        return _cm()

    def delete_object(self, storage_key: str) -> None:
        self.objects.pop(storage_key, None)


@pytest.fixture()
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/trustvault_db",
        JWT_SECRET_KEY=TEST_JWT_SECRET,
        JWT_ALGORITHM="HS256",
        JWT_ISSUER="trustvault",
        JWT_AUDIENCE="trustvault-api",
        ACCESS_TOKEN_EXPIRE_MINUTES=30,
    )
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    get_settings.cache_clear()
    reset_engine()
    return settings


@pytest.fixture()
def memory_storage() -> InMemoryR2:
    return InMemoryR2()


@pytest.fixture()
def audit_hook() -> RecordingUploadAuditHook:
    return RecordingUploadAuditHook()


@pytest.fixture()
def client(
    db_session: Session,
    auth_settings: Settings,
    memory_storage: InMemoryR2,
    audit_hook: RecordingUploadAuditHook,
) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_storage] = lambda: memory_storage
    app.dependency_overrides[get_upload_audit] = lambda: audit_hook
    app.dependency_overrides[get_document_audit] = lambda: audit_hook
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _user(session: Session, *, role: str, email: str | None = None) -> User:
    user = User(
        name=f"{role} Roundtrip",
        email=email or f"{role.lower()}-{uuid.uuid4()}@example.com",
        password_hash=hash_password("roundtrip-password-12"),
        role=role,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _auth(user: User, settings: Settings) -> dict[str, str]:
    token, _ = create_access_token(subject_user_id=user.id, settings=settings)
    return {"Authorization": f"Bearer {token}"}


def _upload_docx(
    client: TestClient,
    headers: dict[str, str],
    *,
    content: bytes = KNOWN_DOCX,
    filename: str = "quarterly-report.docx",
) -> dict:
    response = client.post(
        "/documents",
        headers=headers,
        data={
            "title": "Quarterly Report",
            "category": "Finance",
            "description": "integrity fixture",
        },
        files={"file": (filename, content, DOCX_CONTENT_TYPE)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_upload_download_bytes_identical_and_sha256_matches(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    memory_storage: InMemoryR2,
):
    owner = _user(db_session, role="OWNER")
    headers = _auth(owner, auth_settings)
    expected_sha = sha256_hex_bytes(KNOWN_DOCX)

    created = _upload_docx(client, headers)
    assert created["sha256_checksum"] == expected_sha
    assert created["mime_type"] == DOCX_CONTENT_TYPE
    assert created["file_size"] == len(KNOWN_DOCX)
    assert created["original_filename"] == "quarterly-report.docx"

    doc = db_session.get(Document, uuid.UUID(created["id"]))
    assert doc is not None
    assert doc.storage_key in memory_storage.objects
    stored_bytes, stored_type = memory_storage.objects[doc.storage_key]
    assert stored_bytes == KNOWN_DOCX
    assert stored_type == DOCX_CONTENT_TYPE
    assert hashlib.sha256(stored_bytes).hexdigest() == expected_sha

    download = client.get(f"/documents/{created['id']}/download", headers=headers)
    assert download.status_code == 200
    # Attachment downloads convert DOCX → PDF.
    assert download.content.startswith(b"%PDF")
    assert download.headers["content-type"].startswith("application/pdf")
    assert 'filename="quarterly-report.pdf"' in download.headers["content-disposition"]
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff"
    # Stored object remains original DOCX bytes.
    assert stored_bytes == KNOWN_DOCX
    assert sha256_hex_bytes(stored_bytes) == expected_sha


def test_preview_inline_returns_same_docx_bytes(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    headers = _auth(owner, auth_settings)
    created = _upload_docx(client, headers)

    preview = client.get(
        f"/documents/{created['id']}/download",
        params={"disposition": "inline"},
        headers=headers,
    )
    assert preview.status_code == 200
    assert preview.content == KNOWN_DOCX
    assert preview.headers["content-type"].startswith(DOCX_CONTENT_TYPE)
    assert preview.headers["content-disposition"].startswith("inline;")
    assert 'filename="quarterly-report.docx"' in preview.headers["content-disposition"]


def test_unauthorized_user_cannot_preview_or_download(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    memory_storage: InMemoryR2,
):
    owner = _user(db_session, role="OWNER")
    stranger = _user(db_session, role="VIEWER")
    created = _upload_docx(client, _auth(owner, auth_settings))
    stranger_headers = _auth(stranger, auth_settings)

    for params in ({}, {"disposition": "inline"}):
        response = client.get(
            f"/documents/{created['id']}/download",
            params=params,
            headers=stranger_headers,
        )
        assert response.status_code == 404
        assert KNOWN_DOCX not in response.content
        assert b"TrustVault-roundtrip-marker-9f3c2a" not in response.content


def test_admin_without_grant_cannot_download_or_preview(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    admin = _user(db_session, role="ADMIN")
    created = _upload_docx(client, _auth(owner, auth_settings))

    for params in ({}, {"disposition": "inline"}):
        response = client.get(
            f"/documents/{created['id']}/download",
            params=params,
            headers=_auth(admin, auth_settings),
        )
        assert response.status_code == 404
        assert KNOWN_DOCX not in response.content


def test_revoked_grant_denied_on_next_download(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    created = _upload_docx(client, _auth(owner, auth_settings))
    doc_id = uuid.UUID(created["id"])
    grant = DocumentPermission(
        document_id=doc_id,
        user_id=reader.id,
        permission="READ",
        granted_by=owner.id,
    )
    db_session.add(grant)
    db_session.flush()

    reader_headers = _auth(reader, auth_settings)
    ok = client.get(f"/documents/{doc_id}/download", headers=reader_headers)
    assert ok.status_code == 200
    assert ok.content.startswith(b"%PDF")
    inline = client.get(
        f"/documents/{doc_id}/download",
        params={"disposition": "inline"},
        headers=reader_headers,
    )
    assert inline.content == KNOWN_DOCX

    from datetime import datetime, timezone

    grant.revoked_at = datetime.now(timezone.utc)
    db_session.flush()

    denied = client.get(f"/documents/{doc_id}/download", headers=reader_headers)
    assert denied.status_code == 404
    assert KNOWN_DOCX not in denied.content


def test_missing_storage_object_returns_error_not_fake_file(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    memory_storage: InMemoryR2,
):
    owner = _user(db_session, role="OWNER")
    headers = _auth(owner, auth_settings)
    created = _upload_docx(client, headers)
    doc = db_session.get(Document, uuid.UUID(created["id"]))
    assert doc is not None
    memory_storage.objects.pop(doc.storage_key)

    response = client.get(f"/documents/{created['id']}/download", headers=headers)
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert KNOWN_DOCX not in response.content
    body = response.json()
    assert "detail" in body


def test_storage_failure_is_json_error_not_downloadable_blob(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    memory_storage: InMemoryR2,
):
    owner = _user(db_session, role="OWNER")
    headers = _auth(owner, auth_settings)
    created = _upload_docx(client, headers)

    def boom(_key: str):
        raise StorageOperationError("Storage operation failed")

    memory_storage.open_object = boom  # type: ignore[method-assign]

    response = client.get(f"/documents/{created['id']}/download", headers=headers)
    assert response.status_code == 503
    assert "application/json" in response.headers["content-type"]
    assert response.json()["detail"] == "Document storage is unavailable"


def test_cors_exposes_content_disposition_for_downloads(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    headers = {
        **_auth(owner, auth_settings),
        "Origin": "http://localhost:3000",
    }
    created = _upload_docx(client, headers)
    response = client.get(
        f"/documents/{created['id']}/download",
        headers=headers,
    )
    assert response.status_code == 200
    exposed = response.headers.get("access-control-expose-headers", "")
    exposed_lower = exposed.lower()
    assert "content-disposition" in exposed_lower
    assert "content-type" in exposed_lower
