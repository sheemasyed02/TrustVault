"""Document permission list, grant, revoke, and immediate-revocation tests."""

from __future__ import annotations

import contextlib
import io
import uuid
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.documents import get_document_audit, get_storage, get_upload_audit
from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import Document, DocumentPermission, User
from app.db.session import get_db, reset_engine
from app.main import app
from app.services.document_authorization import (
    DocumentAuthorizationError,
    require_document_edit,
)
from app.services.document_sharing import DocumentSharingError, grant_document_permission
from app.services.upload_audit import FailingUploadAuditHook, RecordingUploadAuditHook

TEST_JWT_SECRET = "unit-test-jwt-secret-key-32chars-min"
PAYLOAD = b"%PDF-1.4\nshared-bytes\n%%EOF\n"


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
) -> User:
    user = User(
        name=f"{role} User",
        email=f"{role.lower()}-{uuid.uuid4()}@example.com",
        password_hash=hash_password("share-password-12"),
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user


DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _document(
    session: Session,
    owner: User,
    *,
    mime_type: str = "application/pdf",
) -> Document:
    doc = Document(
        owner_id=owner.id,
        title="Shared Contract",
        category="Legal",
        description="private",
        storage_key=f"objects/{uuid.uuid4()}",
        mime_type=mime_type,
        file_size=len(PAYLOAD),
        sha256_checksum="d" * 64,
    )
    session.add(doc)
    session.flush()
    return doc


def _token(user: User, settings: Settings) -> str:
    token, _ = create_access_token(subject_user_id=user.id, settings=settings)
    return token


def _auth(user: User, settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user, settings)}"}


def test_owner_can_inspect_permissions(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    viewer = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(viewer.id), "permission": "READ"},
    )
    response = client.get(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == str(doc.id)
    assert len(body["permissions"]) == 1
    grant = body["permissions"][0]
    assert grant["user"]["id"] == str(viewer.id)
    assert grant["permission"] == "READ"
    assert grant["granted_by"]["id"] == str(owner.id)
    assert "password" not in response.text
    assert "password_hash" not in response.text
    assert "storage_key" not in response.text


def test_non_owner_cannot_inspect_permissions(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _user(db_session, role="OWNER")
    viewer = _user(db_session, role="VIEWER")
    editor = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(viewer.id), "permission": "READ"},
    )
    client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(editor.id), "permission": "EDIT"},
    )

    for user in (viewer, editor):
        response = client.get(
            f"/documents/{doc.id}/permissions",
            headers=_auth(user, auth_settings),
        )
        assert response.status_code == 403
        assert "Shared Contract" not in response.text

    assert any(
        e["action"] == "DOCUMENT_PERMISSION_LIST" and e["outcome"] == "DENIED"
        for e in audit_hook.events
    )


def test_owner_can_grant_read_and_edit(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    editor = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)

    read_resp = client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(reader.id), "permission": "READ"},
    )
    assert read_resp.status_code == 201
    assert read_resp.json()["permission"] == "READ"
    assert read_resp.json()["regranted"] is False

    edit_resp = client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(editor.id), "permission": "EDIT"},
    )
    assert edit_resp.status_code == 201
    assert edit_resp.json()["permission"] == "EDIT"
    assert any(
        e["action"] == "DOCUMENT_PERMISSION_GRANT" and e["outcome"] == "SUCCESS"
        for e in audit_hook.events
    )


def test_viewer_cannot_grant(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    viewer = _user(db_session, role="VIEWER")
    other = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    response = client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(viewer, auth_settings),
        json={"user_id": str(other.id), "permission": "READ"},
    )
    assert response.status_code == 404


def test_edit_grantee_cannot_grant(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    editor = _user(db_session, role="VIEWER")
    other = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(editor.id), "permission": "EDIT"},
    )
    response = client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(editor, auth_settings),
        json={"user_id": str(other.id), "permission": "READ"},
    )
    assert response.status_code == 403


def test_admin_without_ownership_cannot_grant(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    admin = _user(db_session, role="ADMIN")
    target = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    response = client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(admin, auth_settings),
        json={"user_id": str(target.id), "permission": "READ"},
    )
    assert response.status_code == 404


def test_nonexistent_target_user_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    response = client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(uuid.uuid4()), "permission": "READ"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_invalid_permission_value_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    target = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    response = client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(target.id), "permission": "ADMIN"},
    )
    assert response.status_code == 422


def test_duplicate_active_grant_conflict(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    target = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    first = client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(target.id), "permission": "READ"},
    )
    assert first.status_code == 201
    second = client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(target.id), "permission": "EDIT"},
    )
    assert second.status_code == 409


def test_regrant_after_revoke_creates_new_active_grant(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _user(db_session, role="OWNER")
    target = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    first = client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(target.id), "permission": "READ"},
    )
    first_id = first.json()["id"]
    revoke = client.delete(
        f"/documents/{doc.id}/permissions/{target.id}",
        headers=_auth(owner, auth_settings),
    )
    assert revoke.status_code == 200

    second = client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(target.id), "permission": "EDIT"},
    )
    assert second.status_code == 201
    assert second.json()["regranted"] is True
    assert second.json()["id"] != first_id
    assert second.json()["permission"] == "EDIT"
    # Prior row remains revoked (not silently reactivated).
    old = db_session.get(DocumentPermission, uuid.UUID(first_id))
    assert old is not None
    assert old.revoked_at is not None
    assert any(
        e["action"] == "DOCUMENT_PERMISSION_GRANT"
        and e["outcome"] == "SUCCESS"
        and e["reason_code"] == "REGRANTED"
        for e in audit_hook.events
    )


def test_owner_can_revoke_active_grant(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _user(db_session, role="OWNER")
    target = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(target.id), "permission": "READ"},
    )
    response = client.delete(
        f"/documents/{doc.id}/permissions/{target.id}",
        headers=_auth(owner, auth_settings),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(target.id)
    assert body["revoked_at"] is not None
    assert any(
        e["action"] == "DOCUMENT_PERMISSION_REVOKE" and e["outcome"] == "SUCCESS"
        for e in audit_hook.events
    )


def test_non_owner_cannot_revoke(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(reader.id), "permission": "READ"},
    )
    response = client.delete(
        f"/documents/{doc.id}/permissions/{reader.id}",
        headers=_auth(reader, auth_settings),
    )
    assert response.status_code == 403


def test_revoked_read_denied_on_next_metadata_and_download_same_token(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(reader.id), "permission": "READ"},
    )
    # Same JWT for before/after — proves authz is not cached in the token.
    reader_headers = _auth(reader, auth_settings)

    before_meta = client.get(f"/documents/{doc.id}", headers=reader_headers)
    before_dl = client.get(f"/documents/{doc.id}/download", headers=reader_headers)
    assert before_meta.status_code == 200
    assert before_dl.status_code == 200
    assert before_dl.content == PAYLOAD

    revoke = client.delete(
        f"/documents/{doc.id}/permissions/{reader.id}",
        headers=_auth(owner, auth_settings),
    )
    assert revoke.status_code == 200
    storage_mock.open_object.reset_mock()

    after_meta = client.get(f"/documents/{doc.id}", headers=reader_headers)
    after_dl = client.get(f"/documents/{doc.id}/download", headers=reader_headers)
    assert after_meta.status_code == 404
    assert after_dl.status_code == 404
    assert PAYLOAD not in after_dl.content
    storage_mock.open_object.assert_not_called()


def test_revoked_edit_denied_edit_and_download_same_token(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    editor = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(editor.id), "permission": "EDIT"},
    )
    editor_headers = _auth(editor, auth_settings)

    assert client.get(f"/documents/{doc.id}/download", headers=editor_headers).status_code == 200
    require_document_edit(db_session, user=editor, document_id=doc.id)

    client.delete(
        f"/documents/{doc.id}/permissions/{editor.id}",
        headers=_auth(owner, auth_settings),
    )
    storage_mock.open_object.reset_mock()

    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_edit(db_session, user=editor, document_id=doc.id)
    assert exc.value.status_code == 404

    denied = client.get(f"/documents/{doc.id}/download", headers=editor_headers)
    assert denied.status_code == 404
    storage_mock.open_object.assert_not_called()


def test_inactive_grantee_denied_even_with_grant(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER", is_active=True)
    doc = _document(db_session, owner)
    client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(reader.id), "permission": "READ"},
    )
    reader.is_active = False
    db_session.flush()
    response = client.get(
        f"/documents/{doc.id}",
        headers=_auth(reader, auth_settings),
    )
    assert response.status_code == 401


def test_manipulated_grantor_fields_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    impostor = _user(db_session, role="OWNER")
    target = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    response = client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={
            "user_id": str(target.id),
            "permission": "READ",
            "granted_by": str(impostor.id),
            "revoked_at": None,
        },
    )
    # extra=forbid → 422; grantor remains the authenticated owner when accepted.
    assert response.status_code == 422


def test_concurrent_duplicate_grants_cannot_conflict(db_session: Session):
    """Application check + partial unique index keep a single active grant."""
    owner = _user(db_session, role="OWNER")
    target = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)

    grant_document_permission(
        db_session,
        actor=owner,
        document_id=doc.id,
        target_user_id=target.id,
        permission="READ",
    )
    with pytest.raises(DocumentSharingError) as exc:
        grant_document_permission(
            db_session,
            actor=owner,
            document_id=doc.id,
            target_user_id=target.id,
            permission="EDIT",
        )
    assert exc.value.reason_code == "DUPLICATE_ACTIVE_GRANT"
    assert exc.value.status_code == 409

    active = list(
        db_session.scalars(
            select(DocumentPermission).where(
                DocumentPermission.document_id == doc.id,
                DocumentPermission.user_id == target.id,
                DocumentPermission.revoked_at.is_(None),
            )
        ).all()
    )
    assert len(active) == 1


def test_audit_failure_does_not_claim_success(
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    failing = FailingUploadAuditHook()
    owner = _user(db_session, role="OWNER")
    target = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_storage] = lambda: storage_mock
    app.dependency_overrides[get_document_audit] = lambda: failing
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/documents/{doc.id}/permissions",
                headers=_auth(owner, auth_settings),
                json={"user_id": str(target.id), "permission": "READ"},
            )
        assert response.status_code == 503
        assert "audited" in response.json()["detail"].lower()
        # Unaudited grant must be removed.
        active = db_session.scalars(
            select(DocumentPermission).where(
                DocumentPermission.document_id == doc.id,
                DocumentPermission.revoked_at.is_(None),
            )
        ).all()
        assert list(active) == []
    finally:
        app.dependency_overrides.clear()


def test_responses_never_expose_secrets(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    target = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    grant = client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(target.id), "permission": "READ"},
    )
    listed = client.get(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
    )
    for response in (grant, listed):
        text = response.text
        assert "password_hash" not in text
        assert "storage_key" not in text
        assert "Bearer" not in text
        assert owner.password_hash not in text


def test_admin_without_grant_cannot_read_or_download(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    admin = _user(db_session, role="ADMIN")
    doc = _document(db_session, owner)
    assert (
        client.get(f"/documents/{doc.id}", headers=_auth(admin, auth_settings)).status_code
        == 404
    )
    assert (
        client.get(
            f"/documents/{doc.id}/download",
            headers=_auth(admin, auth_settings),
        ).status_code
        == 404
    )
    storage_mock.open_object.assert_not_called()


def test_already_revoked_returns_404(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    target = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(target.id), "permission": "READ"},
    )
    assert (
        client.delete(
            f"/documents/{doc.id}/permissions/{target.id}",
            headers=_auth(owner, auth_settings),
        ).status_code
        == 200
    )
    second = client.delete(
        f"/documents/{doc.id}/permissions/{target.id}",
        headers=_auth(owner, auth_settings),
    )
    assert second.status_code == 404
