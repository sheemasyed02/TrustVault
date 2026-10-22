"""Administrator user management and summary — ADMIN-only, no secrets."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.documents import get_document_audit, get_storage, get_upload_audit
from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import Document, User
from app.db.session import get_db, reset_engine
from app.main import app
from app.services.upload_audit import RecordingUploadAuditHook

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
def client(
    db_session: Session,
    auth_settings: Settings,
) -> Generator[TestClient, None, None]:
    recorder = RecordingUploadAuditHook()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_upload_audit] = lambda: recorder
    app.dependency_overrides[get_document_audit] = lambda: recorder
    app.dependency_overrides[get_storage] = lambda: MagicMock()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _user(
    session: Session,
    *,
    role: str,
    email: str | None = None,
    is_active: bool = True,
) -> User:
    user = User(
        name=f"{role} AdminTest",
        email=email or f"{role.lower()}-{uuid.uuid4()}@example.com",
        password_hash=hash_password("admin-test-password-12"),
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user


def _auth(user: User, settings: Settings) -> dict[str, str]:
    token, _ = create_access_token(subject_user_id=user.id, settings=settings)
    return {"Authorization": f"Bearer {token}"}


def test_non_admin_cannot_list_or_patch_users(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    target = _user(db_session, role="VIEWER")
    headers = _auth(owner, auth_settings)
    assert client.get("/admin/users", headers=headers).status_code == 403
    assert client.get("/admin/summary", headers=headers).status_code == 403
    assert (
        client.patch(
            f"/admin/users/{target.id}",
            headers=headers,
            json={"is_active": False},
        ).status_code
        == 403
    )


def test_admin_lists_safe_user_fields_only(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    admin = _user(db_session, role="ADMIN")
    viewer_email = f"viewer-{uuid.uuid4()}@example.com"
    _user(db_session, role="VIEWER", email=viewer_email)
    resp = client.get("/admin/users", headers=_auth(admin, auth_settings))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2
    for row in body["results"]:
        assert "password" not in row
        assert "password_hash" not in row
        assert "access_token" not in row
        assert set(row.keys()) >= {
            "id",
            "name",
            "email",
            "role",
            "is_active",
            "created_at",
            "updated_at",
            "account_status",
        }

    filtered = client.get(
        "/admin/users",
        headers=_auth(admin, auth_settings),
        params={"q": viewer_email, "role": "VIEWER", "is_active": True},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] >= 1
    assert all(row["role"] == "VIEWER" for row in filtered.json()["results"])
    assert all(row["is_active"] is True for row in filtered.json()["results"])


def test_admin_user_profile_and_non_admin_denied(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    admin = _user(db_session, role="ADMIN")
    viewer = _user(db_session, role="VIEWER", email=f"profile-{uuid.uuid4()}@example.com")
    owner = _user(db_session, role="OWNER")

    profile = client.get(
        f"/admin/users/{viewer.id}",
        headers=_auth(admin, auth_settings),
    )
    assert profile.status_code == 200
    body = profile.json()
    assert body["id"] == str(viewer.id)
    assert body["email"] == viewer.email
    assert body["role"] == "VIEWER"
    assert body["account_status"] == "Active"
    assert "activity" in body
    assert body["activity"]["owned_documents"] == 0
    assert "password" not in body
    assert "password_hash" not in body
    assert "access_token" not in body
    assert "storage_key" not in body

    missing = client.get(
        f"/admin/users/{uuid.uuid4()}",
        headers=_auth(admin, auth_settings),
    )
    assert missing.status_code == 404

    assert (
        client.get(
            f"/admin/users/{viewer.id}",
            headers=_auth(viewer, auth_settings),
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/admin/users/{admin.id}",
            headers=_auth(owner, auth_settings),
        ).status_code
        == 403
    )
    assert client.get("/admin/users", headers=_auth(viewer, auth_settings)).status_code == 403


def test_admin_can_deactivate_and_disabled_user_blocked(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    admin = _user(db_session, role="ADMIN")
    viewer = _user(db_session, role="VIEWER")
    viewer_headers = _auth(viewer, auth_settings)

    assert client.get("/users/me", headers=viewer_headers).status_code == 200

    patched = client.patch(
        f"/admin/users/{viewer.id}",
        headers=_auth(admin, auth_settings),
        json={"is_active": False},
    )
    assert patched.status_code == 200
    assert patched.json()["is_active"] is False

    assert client.get("/users/me", headers=viewer_headers).status_code == 401
    assert client.get("/documents", headers=viewer_headers).status_code == 401


def test_cannot_self_deactivate_when_other_admins_exist(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    admin = _user(db_session, role="ADMIN")
    _user(db_session, role="ADMIN")
    resp = client.patch(
        f"/admin/users/{admin.id}",
        headers=_auth(admin, auth_settings),
        json={"is_active": False},
    )
    assert resp.status_code == 400
    assert "own account" in resp.json()["detail"].lower()


def test_cannot_deactivate_last_active_admin(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    from sqlalchemy import select

    admin_a = _user(db_session, role="ADMIN")
    # Shared DB may already contain other active admins (e.g. demo seed).
    for other in db_session.scalars(
        select(User).where(
            User.role == "ADMIN",
            User.is_active.is_(True),
            User.id != admin_a.id,
        )
    ).all():
        other.is_active = False
    db_session.flush()

    resp = client.patch(
        f"/admin/users/{admin_a.id}",
        headers=_auth(admin_a, auth_settings),
        json={"is_active": False},
    )
    assert resp.status_code == 400
    assert "last active administrator" in resp.json()["detail"].lower()


def test_role_not_mass_assignable(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    admin = _user(db_session, role="ADMIN")
    viewer = _user(db_session, role="VIEWER")
    resp = client.patch(
        f"/admin/users/{viewer.id}",
        headers=_auth(admin, auth_settings),
        json={"is_active": True, "role": "ADMIN"},
    )
    assert resp.status_code == 422
    db_session.refresh(viewer)
    assert viewer.role == "VIEWER"


def test_admin_summary_counts(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    admin = _user(db_session, role="ADMIN")
    _user(db_session, role="VIEWER", is_active=True)
    _user(db_session, role="OWNER", is_active=False)
    resp = client.get("/admin/summary", headers=_auth(admin, auth_settings))
    assert resp.status_code == 200
    body = resp.json()
    assert body["users_total"] >= 3
    assert body["users_active"] + body["users_inactive"] == body["users_total"]
    assert body["users_inactive"] >= 1
    assert body["audit_success_total"] >= 0
    assert body["audit_denied_total"] >= 0


def test_admin_audit_metadata_does_not_grant_document_download(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    admin = _user(db_session, role="ADMIN")
    owner = _user(db_session, role="OWNER")
    doc = Document(
        owner_id=owner.id,
        title="Confidential",
        category="Legal",
        storage_key=f"objects/{uuid.uuid4()}",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        file_size=10,
        sha256_checksum="a" * 64,
    )
    db_session.add(doc)
    db_session.flush()

    headers = _auth(admin, auth_settings)
    assert client.get("/admin/audit/events", headers=headers).status_code == 200
    denied = client.get(f"/documents/{doc.id}/download", headers=headers)
    assert denied.status_code == 404
    meta = client.get(f"/documents/{doc.id}", headers=headers)
    assert meta.status_code == 404
