"""In-app DOCX content replace — owner/EDIT can save; READ cannot."""

from __future__ import annotations

import contextlib
import io
import uuid
import zipfile
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.documents import get_document_audit, get_storage
from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import Document, DocumentPermission, User
from app.db.session import get_db, reset_engine
from app.main import app
from app.services.document_content import build_docx_bytes_from_text
from app.services.file_validation import DOCX_MEDIA_TYPE
from app.services.upload_audit import RecordingUploadAuditHook
from app.storage.hashing import sha256_hex_bytes

TEST_JWT_SECRET = "unit-test-jwt-secret-key-32chars-min"


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
    store: dict[str, bytes] = {}

    def upload_bytes(key: str, data: bytes, **kwargs):
        store[key] = bytes(data)
        result = MagicMock()
        result.storage_key = key
        result.size_bytes = len(data)
        result.sha256_hex = sha256_hex_bytes(data)
        return result

    def open_object(key: str):
        if key not in store:
            from app.storage import StorageNotFoundError

            raise StorageNotFoundError("Object not found")
        stream = io.BytesIO(store[key])

        @contextlib.contextmanager
        def _cm():
            try:
                yield stream
            finally:
                stream.close()

        return _cm()

    mock = MagicMock()
    mock.upload_bytes.side_effect = upload_bytes
    mock.open_object.side_effect = open_object
    mock._store = store
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
    app.dependency_overrides[get_document_audit] = lambda: audit_hook
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _user(session: Session, *, role: str, email: str | None = None) -> User:
    user = User(
        name=f"{role} Content",
        email=email or f"{role.lower()}-{uuid.uuid4()}@example.com",
        password_hash=hash_password("content-password-12"),
        role=role,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _auth(user: User, settings: Settings) -> dict[str, str]:
    token, _ = create_access_token(subject_user_id=user.id, settings=settings)
    return {"Authorization": f"Bearer {token}"}


def _docx_doc(session: Session, owner: User, storage_mock: MagicMock) -> Document:
    initial = build_docx_bytes_from_text("Original line")
    key = f"objects/{uuid.uuid4()}"
    storage_mock.upload_bytes(key, initial, content_type=DOCX_MEDIA_TYPE)
    doc = Document(
        owner_id=owner.id,
        title="Editable Memo",
        category="Legal",
        description=None,
        storage_key=key,
        original_filename="memo.docx",
        mime_type=DOCX_MEDIA_TYPE,
        file_size=len(initial),
        sha256_checksum=sha256_hex_bytes(initial),
    )
    session.add(doc)
    session.flush()
    return doc


def test_detail_includes_your_access_for_owner_read_edit(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    editor = _user(db_session, role="VIEWER")
    doc = _docx_doc(db_session, owner, storage_mock)
    db_session.add(
        DocumentPermission(
            document_id=doc.id,
            user_id=reader.id,
            permission="READ",
            granted_by=owner.id,
        )
    )
    db_session.add(
        DocumentPermission(
            document_id=doc.id,
            user_id=editor.id,
            permission="EDIT",
            granted_by=owner.id,
        )
    )
    db_session.flush()

    owner_detail = client.get(f"/documents/{doc.id}", headers=_auth(owner, auth_settings))
    assert owner_detail.status_code == 200
    assert owner_detail.json()["your_access"] == "OWNER"

    read_detail = client.get(f"/documents/{doc.id}", headers=_auth(reader, auth_settings))
    assert read_detail.status_code == 200
    assert read_detail.json()["your_access"] == "READ"

    edit_detail = client.get(f"/documents/{doc.id}", headers=_auth(editor, auth_settings))
    assert edit_detail.status_code == 200
    assert edit_detail.json()["your_access"] == "EDIT"


def test_owner_and_edit_can_replace_content_read_cannot(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    editor = _user(db_session, role="VIEWER")
    doc = _docx_doc(db_session, owner, storage_mock)
    db_session.add(
        DocumentPermission(
            document_id=doc.id,
            user_id=reader.id,
            permission="READ",
            granted_by=owner.id,
        )
    )
    db_session.add(
        DocumentPermission(
            document_id=doc.id,
            user_id=editor.id,
            permission="EDIT",
            granted_by=owner.id,
        )
    )
    db_session.flush()

    denied = client.put(
        f"/documents/{doc.id}/content",
        headers=_auth(reader, auth_settings),
        json={"text": "Hacked"},
    )
    assert denied.status_code == 403

    owner_ok = client.put(
        f"/documents/{doc.id}/content",
        headers=_auth(owner, auth_settings),
        json={"text": "Owner revised\nSecond line"},
    )
    assert owner_ok.status_code == 200
    assert owner_ok.json()["your_access"] == "OWNER"
    assert owner_ok.json()["sha256_checksum"] == sha256_hex_bytes(
        storage_mock._store[doc.storage_key]
    )

    # Stored object is a valid DOCX zip with expected text part.
    with zipfile.ZipFile(io.BytesIO(storage_mock._store[doc.storage_key])) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
        assert "Owner revised" in xml

    editor_ok = client.put(
        f"/documents/{doc.id}/content",
        headers=_auth(editor, auth_settings),
        json={"text": "Editor revised"},
    )
    assert editor_ok.status_code == 200
    assert editor_ok.json()["your_access"] == "EDIT"
    with zipfile.ZipFile(io.BytesIO(storage_mock._store[doc.storage_key])) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
        assert "Editor revised" in xml


def test_build_docx_bytes_roundtrips_structure():
    data = build_docx_bytes_from_text("Hello\nWorld")
    assert data.startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        assert "[Content_Types].xml" in names
        assert "word/document.xml" in names
