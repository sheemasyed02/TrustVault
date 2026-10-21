"""Shared fixtures for the security regression matrix.

Uses the same transactional ``db_session`` as the rest of the suite (rolled
back after each test). Creates isolated users/documents — never relies on
demo seed rows.
"""

from __future__ import annotations

import contextlib
import io
import uuid
from collections.abc import Generator
from datetime import datetime, timezone
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
from app.services.file_validation import DOCX_MEDIA_TYPE
from app.services.upload_audit import RecordingUploadAuditHook

TEST_JWT_SECRET = "security-matrix-jwt-secret-key-32b-min"
DOCX_BYTES = (
    b"PK\x03\x04"
    + b"security-matrix-docx-marker"
    + b"\x00" * 32
)


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
        result.sha256_hex = "a" * 64
        return result

    def open_object(key: str):
        data = store.get(key, DOCX_BYTES)
        stream = io.BytesIO(data)

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
    mock.delete_object.return_value = None
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
    app.dependency_overrides[get_upload_audit] = lambda: audit_hook
    app.dependency_overrides[get_document_audit] = lambda: audit_hook
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def make_user(
    session: Session,
    *,
    role: str,
    is_active: bool = True,
    email: str | None = None,
) -> User:
    user = User(
        name=f"{role} Security",
        email=email or f"{role.lower()}-{uuid.uuid4()}@example.com",
        password_hash=hash_password("security-matrix-password-12"),
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user


def auth_header(user: User, settings: Settings) -> dict[str, str]:
    token, _ = create_access_token(subject_user_id=user.id, settings=settings)
    return {"Authorization": f"Bearer {token}"}


def make_document(
    session: Session,
    owner: User,
    *,
    title: str = "Confidential Matrix Doc",
    storage_key: str | None = None,
) -> Document:
    key = storage_key or f"objects/{uuid.uuid4()}"
    doc = Document(
        owner_id=owner.id,
        title=title,
        category="Security",
        description="matrix-isolated",
        storage_key=key,
        original_filename="matrix.docx",
        mime_type=DOCX_MEDIA_TYPE,
        file_size=len(DOCX_BYTES),
        sha256_checksum="b" * 64,
        created_at=datetime.now(timezone.utc),
    )
    session.add(doc)
    session.flush()
    return doc


def grant_permission(
    session: Session,
    *,
    document: Document,
    user: User,
    permission: str,
    granted_by: User,
) -> DocumentPermission:
    row = DocumentPermission(
        document_id=document.id,
        user_id=user.id,
        permission=permission,
        granted_by=granted_by.id,
    )
    session.add(row)
    session.flush()
    return row
