"""Secure document upload tests with mocked private R2 storage."""

from __future__ import annotations

import io
import logging
import zipfile
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.documents import get_storage, get_upload_audit
from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import Document, User
from app.db.session import get_db, reset_engine
from app.main import app
from app.services.document_upload import upload_document
from app.services.file_validation import MAX_UPLOAD_BYTES
from app.services.upload_audit import RecordingUploadAuditHook
from app.storage import StorageOperationError
from app.storage.hashing import sha256_hex_bytes

TEST_JWT_SECRET = "unit-test-jwt-secret-key-32chars-min"


def _minimal_pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _minimal_png() -> bytes:
    # 1x1 transparent PNG
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )


def _minimal_jpeg() -> bytes:
    return bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707"
        "070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c"
        "1c2837292c30313434341f27393d38323c2e333432ffdb0043010909090c0b0c180d"
        "0d1832211c2132323232323232323232323232323232323232323232323232323232"
        "323232323232323232323232323232323232323232ffc00011080001000103011100"
        "021101031101ffc40014000100000000000000000000000000000000ffc400141001"
        "00000000000000000000000000000000ffda000c0301000210031000003f00bf80ffd9"
    )


def _minimal_docx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
            'package/2006/content-types"></Types>',
        )
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main"><w:body><w:p/></w:body></w:document>',
        )
    return buffer.getvalue()


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
def storage_mock() -> MagicMock:
    mock = MagicMock()
    mock.upload_bytes.return_value = MagicMock()
    mock.delete_object.return_value = None
    return mock


@pytest.fixture()
def audit_hook() -> RecordingUploadAuditHook:
    return RecordingUploadAuditHook()


@pytest.fixture()
def client(
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
    audit_hook: RecordingUploadAuditHook,
) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_storage] = lambda: storage_mock
    app.dependency_overrides[get_upload_audit] = lambda: audit_hook
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _create_user(
    session: Session,
    *,
    role: str,
    is_active: bool = True,
) -> User:
    user = User(
        name=f"{role} Uploader",
        email=f"{role.lower()}-{__import__('uuid').uuid4()}@example.com",
        password_hash=hash_password("upload-password-12"),
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user


def _token(user: User, settings: Settings) -> str:
    token, _ = create_access_token(subject_user_id=user.id, settings=settings)
    return token


def _upload(
    client: TestClient,
    *,
    token: str | None,
    content: bytes,
    filename: str,
    content_type: str,
    title: str = "Q3 Report",
    category: str = "Finance",
    description: str | None = "Optional notes",
    extra_data: dict | None = None,
):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    data = {
        "title": title,
        "category": category,
    }
    if description is not None:
        data["description"] = description
    if extra_data:
        data.update(extra_data)
    return client.post(
        "/documents",
        headers=headers,
        data=data,
        files={"file": (filename, content, content_type)},
    )


def test_unauthenticated_upload_rejected(client: TestClient):
    response = _upload(
        client,
        token=None,
        content=_minimal_pdf(),
        filename="a.pdf",
        content_type="application/pdf",
    )
    assert response.status_code == 401


def test_owner_upload_permitted(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _create_user(db_session, role="OWNER")
    content = _minimal_pdf()
    response = _upload(
        client,
        token=_token(owner, auth_settings),
        content=content,
        filename="report.pdf",
        content_type="application/pdf",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Q3 Report"
    assert body["category"] == "Finance"
    assert body["owner"]["id"] == str(owner.id)
    assert body["mime_type"] == "application/pdf"
    assert body["file_size"] == len(content)
    assert body["sha256_checksum"] == sha256_hex_bytes(content)
    assert "storage_key" not in body
    assert "password" not in body
    storage_mock.upload_bytes.assert_called_once()
    args, kwargs = storage_mock.upload_bytes.call_args
    assert args[0].startswith("objects/")
    assert args[1] == content
    assert kwargs["content_type"] == "application/pdf"
    doc = db_session.scalar(select(Document).where(Document.id == body["id"]))
    assert doc is not None
    assert doc.owner_id == owner.id
    assert doc.storage_key.startswith("objects/")
    assert any(e["outcome"] == "SUCCESS" for e in audit_hook.events)


@pytest.mark.parametrize("role", ["VIEWER", "ADMIN"])
def test_non_owner_roles_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
    role: str,
):
    user = _create_user(db_session, role=role)
    response = _upload(
        client,
        token=_token(user, auth_settings),
        content=_minimal_pdf(),
        filename="a.pdf",
        content_type="application/pdf",
    )
    assert response.status_code == 403
    storage_mock.upload_bytes.assert_not_called()
    assert db_session.scalar(select(Document)) is None


def test_inactive_user_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    user = _create_user(db_session, role="OWNER", is_active=False)
    response = _upload(
        client,
        token=_token(user, auth_settings),
        content=_minimal_pdf(),
        filename="a.pdf",
        content_type="application/pdf",
    )
    assert response.status_code == 401
    storage_mock.upload_bytes.assert_not_called()


def test_client_owner_id_and_storage_key_ignored(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _create_user(db_session, role="OWNER")
    other = _create_user(db_session, role="OWNER")
    response = _upload(
        client,
        token=_token(owner, auth_settings),
        content=_minimal_pdf(),
        filename="a.pdf",
        content_type="application/pdf",
        extra_data={
            "owner_id": str(other.id),
            "storage_key": "client/controlled/path.pdf",
        },
    )
    assert response.status_code == 201
    doc = db_session.scalar(select(Document).where(Document.id == response.json()["id"]))
    assert doc is not None
    assert doc.owner_id == owner.id
    assert doc.storage_key != "client/controlled/path.pdf"
    assert doc.storage_key.startswith("objects/")


@pytest.mark.parametrize(
    ("builder", "filename", "content_type"),
    [
        (_minimal_pdf, "a.pdf", "application/pdf"),
        (_minimal_docx, "a.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        (_minimal_png, "a.png", "image/png"),
        (_minimal_jpeg, "a.jpg", "image/jpeg"),
        (_minimal_jpeg, "a.jpeg", "image/jpeg"),
    ],
)
def test_valid_formats_accepted(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    builder,
    filename: str,
    content_type: str,
):
    owner = _create_user(db_session, role="OWNER")
    response = _upload(
        client,
        token=_token(owner, auth_settings),
        content=builder(),
        filename=filename,
        content_type=content_type,
    )
    assert response.status_code == 201


def test_empty_file_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _create_user(db_session, role="OWNER")
    response = _upload(
        client,
        token=_token(owner, auth_settings),
        content=b"",
        filename="a.pdf",
        content_type="application/pdf",
    )
    assert response.status_code == 400
    storage_mock.upload_bytes.assert_not_called()


def test_oversized_file_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _create_user(db_session, role="OWNER")
    content = b"%PDF-" + (b"x" * (MAX_UPLOAD_BYTES + 10))
    response = _upload(
        client,
        token=_token(owner, auth_settings),
        content=content,
        filename="big.pdf",
        content_type="application/pdf",
    )
    assert response.status_code == 413
    storage_mock.upload_bytes.assert_not_called()


def test_unsupported_extension_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _create_user(db_session, role="OWNER")
    response = _upload(
        client,
        token=_token(owner, auth_settings),
        content=b"hello",
        filename="a.exe",
        content_type="application/octet-stream",
    )
    assert response.status_code == 415
    storage_mock.upload_bytes.assert_not_called()


def test_mime_mismatch_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _create_user(db_session, role="OWNER")
    response = _upload(
        client,
        token=_token(owner, auth_settings),
        content=_minimal_pdf(),
        filename="a.pdf",
        content_type="image/png",
    )
    assert response.status_code == 415
    storage_mock.upload_bytes.assert_not_called()


def test_spoofed_extension_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _create_user(db_session, role="OWNER")
    response = _upload(
        client,
        token=_token(owner, auth_settings),
        content=_minimal_png(),
        filename="not-a-pdf.pdf",
        content_type="application/pdf",
    )
    assert response.status_code == 415
    storage_mock.upload_bytes.assert_not_called()


def test_malformed_docx_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _create_user(db_session, role="OWNER")
    response = _upload(
        client,
        token=_token(owner, auth_settings),
        content=b"PK\x03\x04not-a-real-docx",
        filename="bad.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert response.status_code == 415
    storage_mock.upload_bytes.assert_not_called()


def test_unsafe_filename_does_not_become_storage_key(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _create_user(db_session, role="OWNER")
    response = _upload(
        client,
        token=_token(owner, auth_settings),
        content=_minimal_pdf(),
        filename="../../etc/passwd.pdf",
        content_type="application/pdf",
    )
    assert response.status_code == 201
    key = storage_mock.upload_bytes.call_args.args[0]
    assert ".." not in key
    assert "etc/passwd" not in key
    assert key.startswith("objects/")


def test_invalid_metadata_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _create_user(db_session, role="OWNER")
    response = _upload(
        client,
        token=_token(owner, auth_settings),
        content=_minimal_pdf(),
        filename="a.pdf",
        content_type="application/pdf",
        title="   ",
        category="Finance",
    )
    assert response.status_code == 422
    storage_mock.upload_bytes.assert_not_called()


def test_validation_failure_leaves_no_r2_or_db_record(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _create_user(db_session, role="OWNER")
    _upload(
        client,
        token=_token(owner, auth_settings),
        content=b"not-pdf",
        filename="a.pdf",
        content_type="application/pdf",
    )
    storage_mock.upload_bytes.assert_not_called()
    assert db_session.scalar(select(Document)) is None


def test_r2_failure_does_not_create_document(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _create_user(db_session, role="OWNER")
    storage_mock.upload_bytes.side_effect = StorageOperationError("Storage operation failed")
    response = _upload(
        client,
        token=_token(owner, auth_settings),
        content=_minimal_pdf(),
        filename="a.pdf",
        content_type="application/pdf",
    )
    assert response.status_code == 500
    assert db_session.scalar(select(Document)) is None


def test_db_failure_after_r2_triggers_cleanup(
    db_session: Session,
    storage_mock: MagicMock,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _create_user(db_session, role="OWNER")
    broken = MagicMock(wraps=db_session)
    broken.add.side_effect = lambda obj: db_session.add(obj)
    broken.flush.side_effect = SQLAlchemyError("insert failed")

    with pytest.raises(Exception) as exc:
        upload_document(
            broken,
            owner=owner,
            file_bytes=_minimal_pdf(),
            filename="a.pdf",
            client_content_type="application/pdf",
            title="Title",
            category="Cat",
            description=None,
            storage=storage_mock,
            audit=audit_hook,
        )
    assert getattr(exc.value, "reason_code", "") == "DB_INSERT_FAILED"
    storage_mock.upload_bytes.assert_called_once()
    storage_mock.delete_object.assert_called_once()
    assert any(
        e["reason_code"] == "DB_INSERT_FAILED_CLEANUP_OK" for e in audit_hook.events
    )


def test_cleanup_failure_still_not_success(
    db_session: Session,
    storage_mock: MagicMock,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _create_user(db_session, role="OWNER")
    storage_mock.delete_object.side_effect = StorageOperationError("delete failed")
    broken = MagicMock(wraps=db_session)
    broken.add.side_effect = lambda obj: db_session.add(obj)
    broken.flush.side_effect = SQLAlchemyError("insert failed")

    with pytest.raises(Exception) as exc:
        upload_document(
            broken,
            owner=owner,
            file_bytes=_minimal_pdf(),
            filename="a.pdf",
            client_content_type="application/pdf",
            title="Title",
            category="Cat",
            description=None,
            storage=storage_mock,
            audit=audit_hook,
        )
    assert getattr(exc.value, "status_code", 0) == 500
    assert any(
        e["reason_code"] == "DB_INSERT_FAILED_CLEANUP_FAILED" for e in audit_hook.events
    )
    assert not any(e["outcome"] == "SUCCESS" for e in audit_hook.events)


def test_success_response_is_safe(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _create_user(db_session, role="OWNER")
    response = _upload(
        client,
        token=_token(owner, auth_settings),
        content=_minimal_pdf(),
        filename="a.pdf",
        content_type="application/pdf",
    )
    body = response.json()
    for forbidden in ("storage_key", "password_hash", "R2_", "access_key", "secret"):
        assert forbidden not in str(body)


def test_logs_do_not_include_credentials_or_bytes(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    caplog: pytest.LogCaptureFixture,
):
    owner = _create_user(db_session, role="OWNER")
    content = _minimal_pdf()
    with caplog.at_level(logging.INFO):
        _upload(
            client,
            token=_token(owner, auth_settings),
            content=content,
            filename="a.pdf",
            content_type="application/pdf",
        )
    combined = " | ".join(record.getMessage() for record in caplog.records)
    assert "super-secret" not in combined
    assert content[:20].decode("latin-1", errors="ignore") not in combined


def test_authorization_denial_is_audited(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
):
    viewer = _create_user(db_session, role="VIEWER")
    _upload(
        client,
        token=_token(viewer, auth_settings),
        content=_minimal_pdf(),
        filename="a.pdf",
        content_type="application/pdf",
    )
    assert any(
        e["outcome"] == "DENIED" and e["reason_code"] == "ROLE_NOT_OWNER"
        for e in audit_hook.events
    )
    assert all(e["persisted"] is False for e in audit_hook.events)
