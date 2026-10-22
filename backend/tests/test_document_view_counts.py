"""Document view counting, owner/admin view activity, and IDOR bounds."""

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
from app.services.audit_trail import append_audit_event
from app.services.document_view_audit import VIEW_DEDUPE_SECONDS
from app.services.upload_audit import DurableAuditHook

TEST_JWT_SECRET = "view-count-jwt-secret-key-32charsxx"
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
def _noop_committed_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid independent DENIED audit sessions locking against the test txn."""

    def _noop(**_kwargs):
        return None

    monkeypatch.setattr(
        "app.services.upload_audit.append_audit_event_committed",
        _noop,
    )


@pytest.fixture()
def client(
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
    _noop_committed_audit: None,
) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield db_session

    durable = DurableAuditHook(db_session)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_upload_audit] = lambda: durable
    app.dependency_overrides[get_document_audit] = lambda: durable
    app.dependency_overrides[get_storage] = lambda: storage_mock
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _user(session: Session, *, role: str, email: str | None = None) -> User:
    user = User(
        name=f"{role} ViewerAudit",
        email=email or f"{role.lower()}-{uuid.uuid4()}@example.com",
        password_hash=hash_password("view-audit-password-12"),
        role=role,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _auth(user: User, settings: Settings) -> dict[str, str]:
    token, _ = create_access_token(subject_user_id=user.id, settings=settings)
    return {"Authorization": f"Bearer {token}"}


def _document(session: Session, owner: User, *, title: str = "Viewed Doc") -> Document:
    doc = Document(
        owner_id=owner.id,
        title=title,
        original_filename="view.pdf",
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


def _grant(
    session: Session,
    *,
    document: Document,
    user: User,
    permission: str,
    granted_by: User,
) -> None:
    session.add(
        DocumentPermission(
            document_id=document.id,
            user_id=user.id,
            permission=permission,
            granted_by=granted_by.id,
        )
    )
    session.flush()


def test_authorized_view_creates_event_with_role_snapshot(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    viewer = _user(db_session, role="VIEWER", email="viewer-snap@example.com")
    doc = _document(db_session, owner)
    _grant(
        db_session,
        document=doc,
        user=viewer,
        permission="READ",
        granted_by=owner,
    )

    resp = client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(viewer, auth_settings),
        params={"disposition": "inline"},
    )
    assert resp.status_code == 200

    audit = client.get(
        f"/documents/{doc.id}/audit",
        headers=_auth(owner, auth_settings),
        params={"action": "DOCUMENT_VIEW"},
    )
    assert audit.status_code == 200
    body = audit.json()
    assert body["summary"]["successful_views"] == 1
    assert body["summary"]["external_views"] == 1
    assert body["summary"]["distinct_external_viewers"] == 1
    assert body["summary"]["owner_self_views"] == 0
    assert body["summary"]["distinct_viewers"] == 1
    assert body["summary"]["latest_view_at"] is not None
    assert body["total"] == 1
    row = body["results"][0]
    assert row["action"] == "DOCUMENT_VIEW"
    assert row["outcome"] == "SUCCESS"
    assert row["actor_email"] == "viewer-snap@example.com"
    assert row["metadata"]["actor_role"] == "VIEWER"
    assert row.get("is_owner_self_view") is False
    # Server-generated timestamp (timezone-aware ISO).
    datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))


def test_dedupe_window_prevents_double_count_same_preview(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    headers = _auth(owner, auth_settings)

    assert (
        client.get(
            f"/documents/{doc.id}/download",
            headers=headers,
            params={"disposition": "inline"},
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/documents/{doc.id}/download",
            headers=headers,
            params={"disposition": "inline"},
        ).status_code
        == 200
    )

    audit = client.get(
        f"/documents/{doc.id}/audit",
        headers=headers,
        params={"action": "DOCUMENT_VIEW"},
    )
    summary = audit.json()["summary"]
    # Owner self-views remain in the security trail…
    assert summary["successful_views"] == 1
    assert summary["owner_self_views"] == 1
    # …but are excluded from external dashboard counts.
    assert summary["external_views"] == 0
    assert summary["distinct_external_viewers"] == 0
    assert VIEW_DEDUPE_SECONDS > 0


def test_metadata_get_does_not_count_as_view(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    headers = _auth(owner, auth_settings)
    assert client.get(f"/documents/{doc.id}", headers=headers).status_code == 200
    audit = client.get(
        f"/documents/{doc.id}/audit",
        headers=headers,
        params={"action": "DOCUMENT_VIEW"},
    )
    assert audit.json()["summary"]["successful_views"] == 0


def test_download_does_not_count_as_view(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    headers = _auth(owner, auth_settings)
    assert (
        client.get(f"/documents/{doc.id}/download", headers=headers).status_code
        == 200
    )
    audit = client.get(f"/documents/{doc.id}/audit", headers=headers)
    summary = audit.json()["summary"]
    assert summary["successful_views"] == 0
    assert summary["successful_downloads"] == 1


def test_unauthorized_access_does_not_increase_view_count(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    stranger = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)

    denied = client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(stranger, auth_settings),
        params={"disposition": "inline"},
    )
    assert denied.status_code in {403, 404}
    storage_mock.open_object.assert_not_called()

    audit = client.get(
        f"/documents/{doc.id}/audit",
        headers=_auth(owner, auth_settings),
    )
    # Denied attempts are recorded separately (and never inflate SUCCESS views).
    assert audit.json()["summary"]["successful_views"] == 0


def test_owner_view_activity_and_idor(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner_a = _user(db_session, role="OWNER")
    owner_b = _user(db_session, role="OWNER")
    viewer = _user(db_session, role="VIEWER")
    doc_a = _document(db_session, owner_a, title="A Doc")
    doc_b = _document(db_session, owner_b, title="B Doc")
    append_audit_event(
        db_session,
        action="DOCUMENT_VIEW",
        outcome="SUCCESS",
        actor_id=viewer.id,
        document_id=doc_a.id,
        metadata={"actor_role": "VIEWER"},
    )
    append_audit_event(
        db_session,
        action="DOCUMENT_VIEW",
        outcome="SUCCESS",
        actor_id=viewer.id,
        document_id=doc_b.id,
        metadata={"actor_role": "VIEWER"},
    )

    listed = client.get(
        "/documents/view-activity",
        headers=_auth(owner_a, auth_settings),
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] >= 1
    assert all(row["owner_id"] == str(owner_a.id) for row in body["results"])
    assert any(
        row["document_id"] == str(doc_a.id) and row["total_views"] >= 1
        for row in body["results"]
    )
    assert all(row["document_id"] != str(doc_b.id) for row in body["results"])

    assert (
        client.get(
            f"/documents/{doc_b.id}/audit",
            headers=_auth(owner_a, auth_settings),
        ).status_code
        in {403, 404}
    )
    assert (
        client.get(
            "/documents/view-activity",
            headers=_auth(viewer, auth_settings),
        ).status_code
        == 403
    )


def test_admin_document_views_and_no_content_access(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    admin = _user(db_session, role="ADMIN")
    owner = _user(db_session, role="OWNER", email="owner-views@example.com")
    viewer = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner, title="Secret Brief")
    append_audit_event(
        db_session,
        action="DOCUMENT_VIEW",
        outcome="SUCCESS",
        actor_id=viewer.id,
        document_id=doc.id,
        metadata={"actor_role": "VIEWER", "actor_email": viewer.email},
    )

    listed = client.get(
        "/admin/audit/document-views",
        headers=_auth(admin, auth_settings),
        params={"q": "Secret Brief"},
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["summary"]["total_view_events"] >= 1
    assert any(row["document_id"] == str(doc.id) for row in body["results"])
    match = next(row for row in body["results"] if row["document_id"] == str(doc.id))
    assert match["total_views"] >= 1
    assert match["owner_email"] == "owner-views@example.com"

    # Admin cannot download solely via audit capability.
    storage_mock.open_object.reset_mock()
    assert client.get(
        f"/documents/{doc.id}/download",
        headers=_auth(admin, auth_settings),
    ).status_code in {403, 404}
    storage_mock.open_object.assert_not_called()


def test_view_count_matches_successful_records(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    v1 = _user(db_session, role="VIEWER")
    v2 = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    for actor in (v1, v1, v2):
        append_audit_event(
            db_session,
            action="DOCUMENT_VIEW",
            outcome="SUCCESS",
            actor_id=actor.id,
            document_id=doc.id,
        )
    append_audit_event(
        db_session,
        action="DOCUMENT_VIEW",
        outcome="DENIED",
        actor_id=v2.id,
        document_id=doc.id,
    )

    audit = client.get(
        f"/documents/{doc.id}/audit",
        headers=_auth(owner, auth_settings),
        params={"action": "DOCUMENT_VIEW", "page_size": 100},
    )
    body = audit.json()
    success_rows = [r for r in body["results"] if r["outcome"] == "SUCCESS"]
    # Filtered list may only include DOCUMENT_VIEW; count SUCCESS among them.
    assert body["summary"]["successful_views"] == 3
    assert body["summary"]["distinct_viewers"] == 2
    assert body["summary"]["external_views"] == 3
    assert len(success_rows) == 3


def test_owner_self_views_excluded_from_external_dashboard(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    viewer = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner, title="Counted Externally")
    append_audit_event(
        db_session,
        action="DOCUMENT_VIEW",
        outcome="SUCCESS",
        actor_id=owner.id,
        document_id=doc.id,
    )
    append_audit_event(
        db_session,
        action="DOCUMENT_VIEW",
        outcome="SUCCESS",
        actor_id=viewer.id,
        document_id=doc.id,
    )

    activity = client.get(
        "/documents/view-activity",
        headers=_auth(owner, auth_settings),
    )
    assert activity.status_code == 200
    row = next(
        r for r in activity.json()["results"] if r["document_id"] == str(doc.id)
    )
    assert row["total_views"] == 1
    assert row["distinct_viewers"] == 1
    assert activity.json()["summary"]["total_view_events"] >= 1

    audit = client.get(
        f"/documents/{doc.id}/audit",
        headers=_auth(owner, auth_settings),
        params={"focus": "external_views"},
    )
    assert audit.status_code == 200
    body = audit.json()
    assert body["summary"]["external_views"] == 1
    assert body["summary"]["owner_self_views"] == 1
    assert body["total"] == 1
    assert body["results"][0]["actor_id"] == str(viewer.id)

    own = client.get(
        f"/documents/{doc.id}/audit",
        headers=_auth(owner, auth_settings),
        params={"focus": "owner_views"},
    )
    assert own.status_code == 200
    assert own.json()["total"] == 1
    assert own.json()["results"][0]["actor_id"] == str(owner.id)
    assert own.json()["results"][0]["is_owner_self_view"] is True
