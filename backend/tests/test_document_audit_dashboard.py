"""Owner/admin audit dashboards, view vs download counts, and IDOR bounds."""

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
from app.db.models import AuditEvent, Document, User
from app.db.session import get_db, reset_engine
from app.main import app
from app.services.audit_trail import append_audit_event
from app.services.upload_audit import RecordingUploadAuditHook
from app.storage import StorageError

TEST_JWT_SECRET = "unit-test-jwt-secret-key-32chars-min"
PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


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
def audit_hook() -> RecordingUploadAuditHook:
    return RecordingUploadAuditHook()


@pytest.fixture()
def storage_mock() -> MagicMock:
    mock = MagicMock()

    def _open_object(_key: str):
        stream = io.BytesIO(PDF_BYTES)

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
def client(
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
    storage_mock: MagicMock,
) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_upload_audit] = lambda: audit_hook
    app.dependency_overrides[get_document_audit] = lambda: audit_hook
    app.dependency_overrides[get_storage] = lambda: storage_mock
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _user(
    session: Session,
    *,
    role: str,
    email: str | None = None,
) -> User:
    user = User(
        name=f"{role} AuditDash",
        email=email or f"{role.lower()}-{uuid.uuid4()}@example.com",
        password_hash=hash_password("audit-password-12"),
        role=role,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _auth(user: User, settings: Settings) -> dict[str, str]:
    token, _ = create_access_token(subject_user_id=user.id, settings=settings)
    return {"Authorization": f"Bearer {token}"}


def _document(session: Session, owner: User, *, title: str = "Audit Doc") -> Document:
    doc = Document(
        owner_id=owner.id,
        title=title,
        original_filename="audit.pdf",
        mime_type="application/pdf",
        category="policy",
        description=None,
        storage_key=f"objects/{uuid.uuid4()}.bin",
        file_size=len(PDF_BYTES),
        sha256_checksum="a" * 64,
    )
    session.add(doc)
    session.flush()
    return doc


def test_view_and_download_actions_are_distinct(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    headers = _auth(owner, auth_settings)

    preview = client.get(
        f"/documents/{doc.id}/download",
        headers=headers,
        params={"disposition": "inline"},
    )
    download = client.get(f"/documents/{doc.id}/download", headers=headers)

    assert preview.status_code == 200
    assert download.status_code == 200
    actions = [(e["action"], e["outcome"]) for e in audit_hook.events]
    assert ("DOCUMENT_VIEW", "SUCCESS") in actions
    assert ("DOCUMENT_DOWNLOAD", "SUCCESS") in actions


def test_denied_preview_logged_without_bytes(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    stranger = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)

    resp = client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(stranger, auth_settings),
        params={"disposition": "inline"},
    )
    assert resp.status_code in {403, 404}
    assert PDF_BYTES not in resp.content
    storage_mock.open_object.assert_not_called()
    assert any(
        e["action"] == "DOCUMENT_VIEW" and e["outcome"] == "DENIED"
        for e in audit_hook.events
    )
    assert not any(
        e["action"] == "DOCUMENT_VIEW" and e["outcome"] == "SUCCESS"
        for e in audit_hook.events
    )


def test_owner_audit_summary_counts_and_identities(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER", email="owner-dash@example.com")
    viewer = _user(db_session, role="VIEWER", email="viewer-dash@example.com")
    other_owner = _user(db_session, role="OWNER", email="other-owner@example.com")
    doc = _document(db_session, owner)
    other_doc = _document(db_session, other_owner, title="Other")

    append_audit_event(
        db_session,
        action="DOCUMENT_VIEW",
        outcome="SUCCESS",
        actor_id=viewer.id,
        document_id=doc.id,
    )
    append_audit_event(
        db_session,
        action="DOCUMENT_VIEW",
        outcome="SUCCESS",
        actor_id=viewer.id,
        document_id=doc.id,
    )
    append_audit_event(
        db_session,
        action="DOCUMENT_DOWNLOAD",
        outcome="SUCCESS",
        actor_id=viewer.id,
        document_id=doc.id,
    )
    append_audit_event(
        db_session,
        action="DOCUMENT_VIEW",
        outcome="DENIED",
        actor_id=other_owner.id,
        document_id=doc.id,
        reason_code="NOT_AUTHORIZED",
    )
    append_audit_event(
        db_session,
        action="DOCUMENT_PERMISSION_GRANT",
        outcome="SUCCESS",
        actor_id=owner.id,
        document_id=doc.id,
        target_user_id=viewer.id,
        metadata={"permission": "READ"},
    )
    append_audit_event(
        db_session,
        action="DOCUMENT_METADATA_UPDATE",
        outcome="SUCCESS",
        actor_id=owner.id,
        document_id=doc.id,
        metadata={"changed_fields": ["title"]},
    )
    # Unrelated private history must not leak into this document's summary.
    append_audit_event(
        db_session,
        action="DOCUMENT_DOWNLOAD",
        outcome="SUCCESS",
        actor_id=other_owner.id,
        document_id=other_doc.id,
    )

    resp = client.get(
        f"/documents/{doc.id}/audit",
        headers=_auth(owner, auth_settings),
    )
    assert resp.status_code == 200
    body = resp.json()
    summary = body["summary"]
    assert summary["successful_views"] == 2
    assert summary["successful_downloads"] == 1
    assert summary["denied_access_attempts"] == 1
    assert summary["permission_grants"] == 1
    assert summary["metadata_updates"] == 1

    grant_rows = [
        row for row in body["results"] if row["action"] == "DOCUMENT_PERMISSION_GRANT"
    ]
    assert grant_rows
    assert grant_rows[0]["actor_email"] == "owner-dash@example.com"
    assert grant_rows[0]["target_user_email"] == "viewer-dash@example.com"
    assert grant_rows[0]["metadata"]["permission"] == "READ"

    meta_rows = [
        row for row in body["results"] if row["action"] == "DOCUMENT_METADATA_UPDATE"
    ]
    assert meta_rows
    assert meta_rows[0]["actor_id"] == str(owner.id)


def test_owner_cannot_read_another_owners_audit_by_guessing_id(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner_a = _user(db_session, role="OWNER")
    owner_b = _user(db_session, role="OWNER")
    doc_b = _document(db_session, owner_b)
    append_audit_event(
        db_session,
        action="DOCUMENT_DOWNLOAD",
        outcome="SUCCESS",
        actor_id=owner_b.id,
        document_id=doc_b.id,
    )

    resp = client.get(
        f"/documents/{doc_b.id}/audit",
        headers=_auth(owner_a, auth_settings),
    )
    assert resp.status_code in {403, 404}


def test_grantee_cannot_read_owner_audit(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    viewer = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    append_audit_event(
        db_session,
        action="DOCUMENT_VIEW",
        outcome="SUCCESS",
        actor_id=viewer.id,
        document_id=doc.id,
    )

    resp = client.get(
        f"/documents/{doc.id}/audit",
        headers=_auth(viewer, auth_settings),
    )
    assert resp.status_code in {403, 404}


def test_admin_can_filter_by_owner_and_see_platform_events(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    admin = _user(db_session, role="ADMIN")
    owner = _user(db_session, role="OWNER")
    other = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    other_doc = _document(db_session, other)

    append_audit_event(
        db_session,
        action="DOCUMENT_DOWNLOAD",
        outcome="SUCCESS",
        actor_id=owner.id,
        document_id=doc.id,
    )
    append_audit_event(
        db_session,
        action="DOCUMENT_DOWNLOAD",
        outcome="SUCCESS",
        actor_id=other.id,
        document_id=other_doc.id,
    )
    append_audit_event(
        db_session,
        action="LOGIN",
        outcome="DENIED",
        actor_id=owner.id,
        reason_code="INVALID_CREDENTIALS",
    )

    headers = _auth(admin, auth_settings)
    by_owner = client.get(
        "/admin/audit/events",
        headers=headers,
        params={"owner_id": str(owner.id)},
    )
    assert by_owner.status_code == 200
    owner_body = by_owner.json()
    assert owner_body["total"] >= 1
    assert all(row["document_id"] == str(doc.id) for row in owner_body["results"])

    platform = client.get("/admin/audit/events", headers=headers)
    assert platform.status_code == 200
    assert platform.json()["total"] >= 3


def test_permission_grant_records_actor_target_and_permission(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
):
    owner = _user(db_session, role="OWNER")
    viewer = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)

    resp = client.post(
        f"/documents/{doc.id}/permissions",
        headers=_auth(owner, auth_settings),
        json={"user_id": str(viewer.id), "permission": "EDIT"},
    )
    assert resp.status_code == 201
    grants = [
        e
        for e in audit_hook.events
        if e["action"] == "DOCUMENT_PERMISSION_GRANT" and e["outcome"] == "SUCCESS"
    ]
    assert grants
    assert grants[-1]["actor_id"] == owner.id
    assert grants[-1]["target_user_id"] == viewer.id
    assert grants[-1]["metadata"]["permission"] == "EDIT"


def test_no_audit_mutation_endpoints_for_ordinary_apis(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    admin = _user(db_session, role="ADMIN")
    owner = _user(db_session, role="OWNER")
    headers_admin = _auth(admin, auth_settings)
    headers_owner = _auth(owner, auth_settings)
    fake = uuid.uuid4()

    for headers in (headers_admin, headers_owner):
        assert client.patch(
            f"/admin/audit/events/{fake}", headers=headers
        ).status_code in {404, 405}
        assert client.delete(
            f"/admin/audit/events/{fake}", headers=headers
        ).status_code in {404, 405}
        assert client.put(
            f"/documents/{fake}/audit", headers=headers
        ).status_code in {404, 405, 422}


def test_failed_download_does_not_log_success(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)

    def _fail(_key: str):
        raise StorageError("unavailable")

    storage_mock.open_object.side_effect = _fail

    resp = client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(owner, auth_settings),
    )
    assert resp.status_code == 503
    assert not any(
        e["action"] == "DOCUMENT_DOWNLOAD" and e["outcome"] == "SUCCESS"
        for e in audit_hook.events
    )
    assert any(
        e["action"] == "DOCUMENT_DOWNLOAD" and e["outcome"] == "DENIED"
        for e in audit_hook.events
    )


def test_audit_events_strip_secrets_at_write(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    admin = _user(db_session, role="ADMIN")
    marker = f"secret-strip-{uuid.uuid4()}"
    event = append_audit_event(
        db_session,
        action="LOGIN",
        outcome="DENIED",
        actor_id=admin.id,
        reason_code="INVALID_CREDENTIALS",
        request_id=marker,
        metadata={"password": "should-strip", "note": "ok"},
    )
    assert "password" not in (event.metadata_json or {})
    assert (event.metadata_json or {}).get("note") == "ok"

    loaded = db_session.scalar(
        select(AuditEvent).where(AuditEvent.request_id == marker)
    )
    assert loaded is not None
    assert "password" not in (loaded.metadata_json or {})

    resp = client.get(
        "/admin/audit/events",
        headers=_auth(admin, auth_settings),
        params={"actor_id": str(admin.id)},
    )
    assert resp.status_code == 200
    for row in resp.json()["results"]:
        assert "password" not in row.get("metadata", {})
        assert "access_token" not in row.get("metadata", {})
