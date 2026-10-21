"""Secure metadata PATCH and owner-only DELETE tests."""

from __future__ import annotations

import contextlib
import io
import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.documents import get_document_audit, get_storage, get_upload_audit
from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import Document, DocumentPermission, User
from app.db.session import get_db, reset_engine
from app.main import app
from app.services.upload_audit import RecordingUploadAuditHook
from app.storage import StorageNotFoundError, StorageOperationError

TEST_JWT_SECRET = "unit-test-jwt-secret-key-32chars-min"
PAYLOAD = b"%PDF-1.4\nmutate-bytes\n%%EOF\n"


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
    app.dependency_overrides[get_document_audit] = lambda: audit_hook
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _user(session: Session, *, role: str = "VIEWER", is_active: bool = True) -> User:
    user = User(
        name=f"{role} User",
        email=f"{role.lower()}-{uuid.uuid4()}@example.com",
        password_hash=hash_password("mutate-password-12"),
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user


def _document(session: Session, owner: User, **kwargs) -> Document:
    doc = Document(
        owner_id=owner.id,
        title=kwargs.get("title", "Original Title"),
        category=kwargs.get("category", "Finance"),
        description=kwargs.get("description", "Original description"),
        storage_key=kwargs.get("storage_key", f"objects/{uuid.uuid4()}"),
        mime_type="application/pdf",
        file_size=len(PAYLOAD),
        sha256_checksum="e" * 64,
    )
    session.add(doc)
    session.flush()
    return doc


def _grant(
    session: Session,
    *,
    document: Document,
    user: User,
    permission: str,
    granted_by: User,
) -> DocumentPermission:
    grant = DocumentPermission(
        document_id=document.id,
        user_id=user.id,
        permission=permission,
        granted_by=granted_by.id,
    )
    session.add(grant)
    session.flush()
    return grant


def _auth(user: User, settings: Settings) -> dict[str, str]:
    token, _ = create_access_token(subject_user_id=user.id, settings=settings)
    return {"Authorization": f"Bearer {token}"}


def test_owner_can_edit_title(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    response = client.patch(
        f"/documents/{doc.id}",
        headers=_auth(owner, auth_settings),
        json={"title": "Updated Title"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"
    assert response.json()["category"] == "Finance"
    assert "storage_key" not in response.json()


def test_owner_can_edit_category_and_description(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    response = client.patch(
        f"/documents/{doc.id}",
        headers=_auth(owner, auth_settings),
        json={"category": "Legal", "description": "New notes"},
    )
    assert response.status_code == 200
    assert response.json()["category"] == "Legal"
    assert response.json()["description"] == "New notes"


def test_edit_grantee_can_edit_metadata(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    editor = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    _grant(
        db_session, document=doc, user=editor, permission="EDIT", granted_by=owner
    )
    response = client.patch(
        f"/documents/{doc.id}",
        headers=_auth(editor, auth_settings),
        json={"title": "Editor Title"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Editor Title"
    assert response.json()["owner"]["id"] == str(owner.id)


def test_read_grantee_cannot_edit(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    _grant(
        db_session, document=doc, user=reader, permission="READ", granted_by=owner
    )
    response = client.patch(
        f"/documents/{doc.id}",
        headers=_auth(reader, auth_settings),
        json={"title": "Nope"},
    )
    assert response.status_code == 403
    assert any(
        e["action"] == "DOCUMENT_METADATA_UPDATE" and e["outcome"] == "DENIED"
        for e in audit_hook.events
    )


def test_unshared_user_cannot_edit(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    stranger = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    response = client.patch(
        f"/documents/{doc.id}",
        headers=_auth(stranger, auth_settings),
        json={"title": "Nope"},
    )
    assert response.status_code == 404


def test_admin_without_grant_cannot_edit(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    admin = _user(db_session, role="ADMIN")
    doc = _document(db_session, owner)
    response = client.patch(
        f"/documents/{doc.id}",
        headers=_auth(admin, auth_settings),
        json={"title": "Admin"},
    )
    assert response.status_code == 404


def test_inactive_account_cannot_edit(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER", is_active=False)
    doc = _document(db_session, owner)
    response = client.patch(
        f"/documents/{doc.id}",
        headers=_auth(owner, auth_settings),
        json={"title": "Inactive"},
    )
    assert response.status_code == 401


def test_revoked_edit_grantee_cannot_edit_next_request(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    editor = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(editor.id), "permission": "EDIT"},
    )
    headers = _auth(editor, auth_settings)
    assert (
        client.patch(
            f"/documents/{doc.id}",
            headers=headers,
            json={"title": "Before Revoke"},
        ).status_code
        == 200
    )
    client.delete(
        f"/documents/{doc.id}/permissions/{editor.id}",
        headers=_auth(owner, auth_settings),
    )
    denied = client.patch(
        f"/documents/{doc.id}",
        headers=headers,
        json={"title": "After Revoke"},
    )
    assert denied.status_code == 404


def test_owner_id_and_storage_key_cannot_be_changed(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    other = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    original_key = doc.storage_key
    response = client.patch(
        f"/documents/{doc.id}",
        headers=_auth(owner, auth_settings),
        json={
            "title": "Ok",
            "owner_id": str(other.id),
            "storage_key": "objects/evil",
        },
    )
    assert response.status_code == 422
    db_session.refresh(doc)
    assert doc.owner_id == owner.id
    assert doc.storage_key == original_key


def test_size_checksum_mime_cannot_be_overwritten(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    response = client.patch(
        f"/documents/{doc.id}",
        headers=_auth(owner, auth_settings),
        json={
            "file_size": 1,
            "sha256_checksum": "f" * 64,
            "mime_type": "image/png",
        },
    )
    assert response.status_code == 422
    db_session.refresh(doc)
    assert doc.file_size == len(PAYLOAD)
    assert doc.sha256_checksum == "e" * 64
    assert doc.mime_type == "application/pdf"


def test_unsupported_and_invalid_metadata_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    assert (
        client.patch(
            f"/documents/{doc.id}",
            headers=_auth(owner, auth_settings),
            json={"deleted_at": datetime.now(timezone.utc).isoformat()},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/documents/{doc.id}",
            headers=_auth(owner, auth_settings),
            json={"title": ""},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/documents/{doc.id}",
            headers=_auth(owner, auth_settings),
            json={"title": "x" * 300},
        ).status_code
        == 422
    )


def test_noop_update_returns_success_with_no_changes_audit(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner, title="Same")
    response = client.patch(
        f"/documents/{doc.id}",
        headers=_auth(owner, auth_settings),
        json={"title": "Same"},
    )
    assert response.status_code == 200
    assert any(
        e["action"] == "DOCUMENT_METADATA_UPDATE"
        and e["outcome"] == "SUCCESS"
        and e["reason_code"] == "NO_CHANGES"
        and e["changed_fields"] == []
        for e in audit_hook.events
    )


def test_owner_can_delete_document(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    key = doc.storage_key
    response = client.delete(
        f"/documents/{doc.id}",
        headers=_auth(owner, auth_settings),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(doc.id)
    assert body["storage_cleanup"] == "completed"
    assert body["deleted_at"] is not None
    storage_mock.delete_object.assert_called_once_with(key)
    db_session.refresh(doc)
    assert doc.deleted_at is not None
    assert any(
        e["action"] == "DOCUMENT_DELETE" and e["outcome"] == "SUCCESS"
        for e in audit_hook.events
    )


def test_read_and_edit_grantee_cannot_delete(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
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
    assert (
        client.delete(
            f"/documents/{doc.id}",
            headers=_auth(reader, auth_settings),
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/documents/{doc.id}",
            headers=_auth(editor, auth_settings),
        ).status_code
        == 403
    )
    storage_mock.delete_object.assert_not_called()


def test_admin_without_ownership_cannot_delete(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    admin = _user(db_session, role="ADMIN")
    doc = _document(db_session, owner)
    response = client.delete(
        f"/documents/{doc.id}",
        headers=_auth(admin, auth_settings),
    )
    assert response.status_code == 404
    storage_mock.delete_object.assert_not_called()


def test_deleted_document_not_listable_readable_or_downloadable(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    assert (
        client.delete(
            f"/documents/{doc.id}",
            headers=_auth(owner, auth_settings),
        ).status_code
        == 200
    )
    storage_mock.open_object.reset_mock()
    listed = client.get("/documents", headers=_auth(owner, auth_settings))
    assert listed.json()["total"] == 0
    assert (
        client.get(f"/documents/{doc.id}", headers=_auth(owner, auth_settings)).status_code
        == 404
    )
    assert (
        client.get(
            f"/documents/{doc.id}/download",
            headers=_auth(owner, auth_settings),
        ).status_code
        == 404
    )
    storage_mock.open_object.assert_not_called()


def test_r2_already_absent_is_successful_cleanup(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    storage_mock.delete_object.side_effect = StorageNotFoundError("Object not found")
    response = client.delete(
        f"/documents/{doc.id}",
        headers=_auth(owner, auth_settings),
    )
    assert response.status_code == 200
    assert response.json()["storage_cleanup"] == "already_absent"
    db_session.refresh(doc)
    assert doc.deleted_at is not None


def test_r2_deletion_failure_does_not_claim_complete_success(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    storage_mock.delete_object.side_effect = StorageOperationError("network down")
    response = client.delete(
        f"/documents/{doc.id}",
        headers=_auth(owner, auth_settings),
    )
    assert response.status_code == 503
    assert "storage cleanup failed" in response.json()["detail"].lower()
    db_session.refresh(doc)
    # Soft-delete retained so the document is not served.
    assert doc.deleted_at is not None
    assert (
        client.get(f"/documents/{doc.id}", headers=_auth(owner, auth_settings)).status_code
        == 404
    )
    assert any(
        e["action"] == "DOCUMENT_DELETE"
        and e["outcome"] == "FAILURE"
        and e["reason_code"] == "STORAGE_DELETE_FAILED"
        for e in audit_hook.events
    )


def test_database_failure_does_not_delete_storage(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)

    from app.services import document_deletion as deletion_mod

    original_flush = db_session.flush

    def boom(*args, **kwargs):
        raise SQLAlchemyError("db down")

    # Fail only the soft-delete flush path by patching after authz.
    calls = {"n": 0}
    real_require = deletion_mod.require_document_delete

    def require_then_break(session, **kwargs):
        doc_obj = real_require(session, **kwargs)
        session.flush = boom  # type: ignore[method-assign]
        return doc_obj

    monkeypatch.setattr(deletion_mod, "require_document_delete", require_then_break)
    response = client.delete(
        f"/documents/{doc.id}",
        headers=_auth(owner, auth_settings),
    )
    assert response.status_code == 503
    storage_mock.delete_object.assert_not_called()
    db_session.flush = original_flush  # type: ignore[method-assign]
    db_session.refresh(doc)
    assert doc.deleted_at is None


def test_repeated_deletion_returns_not_found(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    assert (
        client.delete(
            f"/documents/{doc.id}",
            headers=_auth(owner, auth_settings),
        ).status_code
        == 200
    )
    second = client.delete(
        f"/documents/{doc.id}",
        headers=_auth(owner, auth_settings),
    )
    assert second.status_code == 404
    assert "successfully" not in second.text.lower()


def test_denied_deletion_is_audited(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _user(db_session, role="OWNER")
    editor = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    _grant(
        db_session, document=doc, user=editor, permission="EDIT", granted_by=owner
    )
    client.delete(
        f"/documents/{doc.id}",
        headers=_auth(editor, auth_settings),
    )
    assert any(
        e["action"] == "DOCUMENT_DELETE" and e["outcome"] == "DENIED"
        for e in audit_hook.events
    )


def test_no_ordinary_audit_mutation_endpoints():
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    methods = []
    for route in app.routes:
        if not hasattr(route, "methods"):
            continue
        for method in route.methods or []:
            methods.append((method, route.path))
    assert not any(
        path.startswith("/audit") and method in {"PUT", "PATCH", "DELETE"}
        for method, path in methods
    )
    assert "/audit_events" not in paths


def test_edit_grantee_cannot_change_owner_via_patch(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    editor = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    _grant(
        db_session, document=doc, user=editor, permission="EDIT", granted_by=owner
    )
    response = client.patch(
        f"/documents/{doc.id}",
        headers=_auth(editor, auth_settings),
        json={"owner_id": str(editor.id)},
    )
    assert response.status_code == 422
    db_session.refresh(doc)
    assert doc.owner_id == owner.id


def test_concurrency_policy_revoke_before_edit_is_denied(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    """Documented policy: revoke committed before edit authz denies the PATCH.

    Full cross-transaction FOR UPDATE race is not claimed as eliminated under
    READ COMMITTED; this test proves the same-token revoke-then-edit path.
    """
    owner = _user(db_session, role="OWNER")
    editor = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(editor.id), "permission": "EDIT"},
    )
    editor_headers = _auth(editor, auth_settings)
    client.delete(
        f"/documents/{doc.id}/permissions/{editor.id}",
        headers=_auth(owner, auth_settings),
    )
    response = client.patch(
        f"/documents/{doc.id}",
        headers=editor_headers,
        json={"title": "Race"},
    )
    assert response.status_code == 404
