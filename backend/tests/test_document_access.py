"""Authorized document list, metadata, and download endpoint tests."""

from __future__ import annotations

import contextlib
import inspect
import io
import re
import uuid
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
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
from app.services.document_download import safe_download_filename
from app.services.upload_audit import RecordingUploadAuditHook
from app.storage import StorageNotFoundError, StorageOperationError

TEST_JWT_SECRET = "unit-test-jwt-secret-key-32chars-min"
PAYLOAD = b"%PDF-1.4\nconfidential-bytes\n%%EOF\n"


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

    def _open_object(_key: str):
        stream = io.BytesIO(PAYLOAD)

        @contextlib.contextmanager
        def _cm():
            try:
                yield stream
            finally:
                stream.close()

        return _cm()

    mock.open_object.side_effect = _open_object
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


def _user(
    session: Session,
    *,
    role: str = "VIEWER",
    is_active: bool = True,
    email: str | None = None,
) -> User:
    user = User(
        name=f"{role} User",
        email=email or f"{role.lower()}-{uuid.uuid4()}@example.com",
        password_hash=hash_password("access-password-12"),
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user


def _document(
    session: Session,
    owner: User,
    *,
    title: str = "Confidential Contract",
    category: str = "HR",
    deleted: bool = False,
    created_at: datetime | None = None,
) -> Document:
    doc = Document(
        owner_id=owner.id,
        title=title,
        category=category,
        description="private-description",
        storage_key=f"objects/{uuid.uuid4()}",
        mime_type="application/pdf",
        file_size=len(PAYLOAD),
        sha256_checksum="b" * 64,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    session.add(doc)
    session.flush()
    if created_at is not None:
        doc.created_at = created_at
        session.flush()
    return doc


def _grant(
    session: Session,
    *,
    document: Document,
    user: User,
    permission: str,
    granted_by: User,
    revoked: bool = False,
) -> DocumentPermission:
    grant = DocumentPermission(
        document_id=document.id,
        user_id=user.id,
        permission=permission,
        granted_by=granted_by.id,
        revoked_at=datetime.now(timezone.utc) if revoked else None,
    )
    session.add(grant)
    session.flush()
    return grant


def _token(user: User, settings: Settings) -> str:
    token, _ = create_access_token(subject_user_id=user.id, settings=settings)
    return token


def _auth(user: User, settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user, settings)}"}


def test_owner_lists_own_documents(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    other = _user(db_session, role="OWNER")
    mine = _document(db_session, owner, title="Mine")
    _document(db_session, other, title="Secret Other")

    response = client.get("/documents", headers=_auth(owner, auth_settings))
    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body["results"]}
    assert str(mine.id) in ids
    assert body["total"] == 1
    assert all(item["title"] != "Secret Other" for item in body["results"])
    assert "storage_key" not in body["results"][0]
    assert "description" not in body["results"][0]


def test_read_grantee_lists_only_granted(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    granted = _document(db_session, owner, title="Shared Read")
    hidden = _document(db_session, owner, title="Not Shared")
    _grant(
        db_session,
        document=granted,
        user=reader,
        permission="READ",
        granted_by=owner,
    )

    response = client.get("/documents", headers=_auth(reader, auth_settings))
    assert response.status_code == 200
    titles = {item["title"] for item in response.json()["results"]}
    assert titles == {"Shared Read"}
    assert str(hidden.id) not in {item["id"] for item in response.json()["results"]}


def test_edit_grantee_lists_only_granted(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    editor = _user(db_session, role="VIEWER")
    granted = _document(db_session, owner, title="Shared Edit")
    _document(db_session, owner, title="Hidden")
    _grant(
        db_session,
        document=granted,
        user=editor,
        permission="EDIT",
        granted_by=owner,
    )

    response = client.get("/documents", headers=_auth(editor, auth_settings))
    assert response.status_code == 200
    assert {item["title"] for item in response.json()["results"]} == {"Shared Edit"}


def test_unrelated_user_documents_absent_from_list(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    stranger = _user(db_session, role="VIEWER")
    _document(db_session, owner, title="Invisible")

    response = client.get("/documents", headers=_auth(stranger, auth_settings))
    assert response.status_code == 200
    assert response.json()["results"] == []
    assert response.json()["total"] == 0


def test_search_does_not_reveal_inaccessible_titles(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    stranger = _user(db_session, role="VIEWER")
    _document(db_session, owner, title="UltraSecretAlpha")

    response = client.get(
        "/documents",
        headers=_auth(stranger, auth_settings),
        params={"title": "UltraSecretAlpha"},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["results"] == []


def test_owner_filter_cannot_bypass_visibility(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    stranger = _user(db_session, role="VIEWER")
    _document(db_session, owner, title="Owned")

    response = client.get(
        "/documents",
        headers=_auth(stranger, auth_settings),
        params={"owner_id": str(owner.id)},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_metadata_owner_read_edit_grantee(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    editor = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    _grant(
        db_session, document=doc, user=reader, permission="READ", granted_by=owner
    )
    _grant(
        db_session, document=doc, user=editor, permission="EDIT", granted_by=owner
    )

    for user in (owner, reader, editor):
        response = client.get(
            f"/documents/{doc.id}",
            headers=_auth(user, auth_settings),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(doc.id)
        assert body["title"] == "Confidential Contract"
        assert body["description"] == "private-description"
        assert body["owner"]["id"] == str(owner.id)
        assert "storage_key" not in body


def test_unshared_user_cannot_retrieve_metadata(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _user(db_session, role="OWNER")
    stranger = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)

    response = client.get(
        f"/documents/{doc.id}",
        headers=_auth(stranger, auth_settings),
    )
    assert response.status_code == 404
    assert "Confidential" not in response.text
    assert any(
        e["action"] == "DOCUMENT_METADATA_READ" and e["outcome"] == "DENIED"
        for e in audit_hook.events
    )


def test_unauthorized_download_returns_no_bytes(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    stranger = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)

    response = client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(stranger, auth_settings),
    )
    assert response.status_code == 404
    assert PAYLOAD not in response.content
    assert b"confidential-bytes" not in response.content
    storage_mock.open_object.assert_not_called()


def test_authorized_download_returns_bytes(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)

    response = client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(owner, auth_settings),
    )
    assert response.status_code == 200
    assert response.content == PAYLOAD
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"].startswith("attachment;")
    assert ".pdf" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in response.headers["cache-control"]
    storage_mock.open_object.assert_called_once_with(doc.storage_key)
    assert any(
        e["action"] == "DOCUMENT_DOWNLOAD" and e["outcome"] == "SUCCESS"
        for e in audit_hook.events
    )


def test_read_and_edit_grantee_can_download(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    editor = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    _grant(
        db_session, document=doc, user=reader, permission="READ", granted_by=owner
    )
    _grant(
        db_session, document=doc, user=editor, permission="EDIT", granted_by=owner
    )

    for user in (reader, editor):
        response = client.get(
            f"/documents/{doc.id}/download",
            headers=_auth(user, auth_settings),
        )
        assert response.status_code == 200
        assert response.content == PAYLOAD


def test_revoked_grant_denied_on_next_download(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    grant = _grant(
        db_session, document=doc, user=reader, permission="READ", granted_by=owner
    )

    ok = client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(reader, auth_settings),
    )
    assert ok.status_code == 200

    grant.revoked_at = datetime.now(timezone.utc)
    db_session.flush()
    storage_mock.open_object.reset_mock()

    denied = client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(reader, auth_settings),
    )
    assert denied.status_code == 404
    assert PAYLOAD not in denied.content
    storage_mock.open_object.assert_not_called()


def test_inactive_user_denied_list_and_download(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER", is_active=False)
    doc = _document(db_session, owner)
    headers = _auth(owner, auth_settings)

    assert client.get("/documents", headers=headers).status_code == 401
    assert client.get(f"/documents/{doc.id}", headers=headers).status_code == 401
    assert client.get(f"/documents/{doc.id}/download", headers=headers).status_code == 401
    storage_mock.open_object.assert_not_called()


def test_admin_without_grant_cannot_download(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    admin = _user(db_session, role="ADMIN")
    doc = _document(db_session, owner)

    response = client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(admin, auth_settings),
    )
    assert response.status_code == 404
    storage_mock.open_object.assert_not_called()

    listed = client.get("/documents", headers=_auth(admin, auth_settings))
    assert listed.status_code == 200
    assert listed.json()["total"] == 0


def test_deleted_documents_excluded(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner, deleted=True)

    listed = client.get("/documents", headers=_auth(owner, auth_settings))
    assert listed.json()["total"] == 0

    meta = client.get(f"/documents/{doc.id}", headers=_auth(owner, auth_settings))
    assert meta.status_code == 404

    download = client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(owner, auth_settings),
    )
    assert download.status_code == 404
    storage_mock.open_object.assert_not_called()


def test_forged_document_id_does_not_bypass(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    forged = uuid.uuid4()
    response = client.get(
        f"/documents/{forged}/download",
        headers=_auth(owner, auth_settings),
    )
    assert response.status_code == 404
    storage_mock.open_object.assert_not_called()


def test_pagination_and_filters_validated(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    now = datetime.now(timezone.utc)
    older = _document(
        db_session,
        owner,
        title="Alpha Report",
        category="Finance",
        created_at=now - timedelta(days=5),
    )
    newer = _document(
        db_session,
        owner,
        title="Beta Report",
        category="Legal",
        created_at=now - timedelta(days=1),
    )

    page = client.get(
        "/documents",
        headers=_auth(owner, auth_settings),
        params={"page": 1, "page_size": 1},
    )
    assert page.status_code == 200
    body = page.json()
    assert body["page_size"] == 1
    assert body["total"] == 2
    assert body["total_pages"] == 2
    assert len(body["results"]) == 1
    # Stable ordering: newest first
    assert body["results"][0]["id"] == str(newer.id)

    page2 = client.get(
        "/documents",
        headers=_auth(owner, auth_settings),
        params={"page": 2, "page_size": 1},
    )
    assert page2.json()["results"][0]["id"] == str(older.id)

    filtered = client.get(
        "/documents",
        headers=_auth(owner, auth_settings),
        params={"category": "Finance", "title": "Alpha"},
    )
    assert filtered.json()["total"] == 1
    assert filtered.json()["results"][0]["id"] == str(older.id)

    bad = client.get(
        "/documents",
        headers=_auth(owner, auth_settings),
        params={"page_size": 101},
    )
    assert bad.status_code == 422

    bad_range = client.get(
        "/documents",
        headers=_auth(owner, auth_settings),
        params={
            "created_from": (now + timedelta(days=1)).isoformat(),
            "created_to": (now - timedelta(days=1)).isoformat(),
        },
    )
    assert bad_range.status_code == 422


def test_r2_never_called_for_unauthorized_download(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    stranger = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(stranger, auth_settings),
    )
    storage_mock.open_object.assert_not_called()
    storage_mock.iter_object_chunks.assert_not_called()


def test_r2_missing_object_handled_safely(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)

    @contextlib.contextmanager
    def missing(_key: str):
        raise StorageNotFoundError("Object not found")
        yield  # pragma: no cover

    storage_mock.open_object.side_effect = missing
    response = client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(owner, auth_settings),
    )
    assert response.status_code == 503
    assert "storage_key" not in response.text
    assert doc.storage_key not in response.text
    assert any(
        e["action"] == "DOCUMENT_DOWNLOAD" and e["outcome"] == "FAILURE"
        for e in audit_hook.events
    )


def test_r2_network_failure_handled_safely(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)

    @contextlib.contextmanager
    def boom(_key: str):
        raise StorageOperationError("network down")
        yield  # pragma: no cover

    storage_mock.open_object.side_effect = boom
    response = client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(owner, auth_settings),
    )
    assert response.status_code == 503
    assert "network down" not in response.text


def test_streaming_closes_storage_response(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    closed = {"value": False}

    def _open_object(_key: str):
        stream = io.BytesIO(PAYLOAD)

        @contextlib.contextmanager
        def _cm():
            try:
                yield stream
            finally:
                stream.close()
                closed["value"] = True

        return _cm()

    storage_mock.open_object.side_effect = _open_object
    response = client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(owner, auth_settings),
    )
    assert response.status_code == 200
    assert response.content == PAYLOAD
    assert closed["value"] is True


def test_filename_header_injection_prevented():
    doc = Document(
        owner_id=uuid.uuid4(),
        title='evil\r\nContent-Disposition: attachment; filename="pwned.pdf"',
        category="HR",
        storage_key="objects/x",
        mime_type="application/pdf",
        file_size=1,
        sha256_checksum="c" * 64,
    )
    filename = safe_download_filename(doc)
    assert "\r" not in filename
    assert "\n" not in filename
    assert '"' not in filename
    # Header value must remain a single safe token for Content-Disposition.
    assert re.fullmatch(r"[A-Za-z0-9._-]+", filename)


def test_download_endpoint_requires_authorization_check():
    """Regression: download route must call require_document_read before R2."""
    from app.api import documents as documents_api

    source = inspect.getsource(documents_api.download_document)
    assert "require_document_read" in source
    assert "open_download_stream" in source
    # Authorization must appear before storage open in source order.
    assert source.index("require_document_read") < source.index("open_download_stream")


def test_download_denials_and_successes_audited(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _user(db_session, role="OWNER")
    stranger = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)

    client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(stranger, auth_settings),
    )
    client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(owner, auth_settings),
    )
    outcomes = [
        (e["action"], e["outcome"], e["persisted"])
        for e in audit_hook.events
        if e["action"] == "DOCUMENT_DOWNLOAD"
    ]
    assert ("DOCUMENT_DOWNLOAD", "DENIED", False) in outcomes
    assert ("DOCUMENT_DOWNLOAD", "SUCCESS", False) in outcomes


def test_no_duplicate_when_owner_also_has_grant(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    _grant(
        db_session, document=doc, user=owner, permission="READ", granted_by=owner
    )
    response = client.get("/documents", headers=_auth(owner, auth_settings))
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert len(response.json()["results"]) == 1
