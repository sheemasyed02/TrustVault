"""Public registration, login session, and owner-promotion workflow."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import Document, DocumentPermission, OwnerPromotionRequest, User
from app.db.session import get_db, reset_engine
from app.main import app
from app.services.file_validation import DOCX_MEDIA_TYPE

TEST_JWT_SECRET = "register-promo-jwt-secret-key-32bxx"


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
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    """Avoid cross-connection audit-chain lock waits under the test SAVEPOINT.

    DENIED paths use ``append_audit_event_committed`` (separate session). That
    blocks on the advisory lock while SUCCESS events remain uncommitted in the
    test transaction. No-op the independent writer here; SUCCESS still flushes
    on the request session.
    """

    def _noop_committed(**_kwargs):
        return None

    monkeypatch.setattr("app.api.auth.append_audit_event_committed", _noop_committed)
    monkeypatch.setattr(
        "app.api.promotions.append_audit_event_committed", _noop_committed
    )

    def override_get_db():
        yield db_session

    def override_settings():
        return auth_settings

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _token(user: User, settings: Settings) -> str:
    token, _ = create_access_token(subject_user_id=user.id, settings=settings)
    return token


def _auth(user: User, settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user, settings)}"}


def _user(
    session: Session,
    *,
    role: str,
    email: str | None = None,
    password: str = "secure-password-12",
) -> User:
    user = User(
        name=f"{role} User",
        email=email or f"{role.lower()}-{uuid.uuid4()}@example.com",
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------


def test_register_creates_viewer_with_hashed_password(
    client: TestClient,
    db_session: Session,
):
    email = f"new.viewer-{uuid.uuid4()}@example.com"
    password = "secure-password-12"
    ok = client.post(
        "/auth/register",
        json={"name": "New Viewer", "email": email, "password": password},
    )
    assert ok.status_code == 201
    body = ok.json()
    assert body["role"] == "VIEWER"
    assert "password" not in body
    assert "password_hash" not in body
    assert "access_token" not in body

    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    assert user.role == "VIEWER"
    assert user.password_hash != password
    assert verify_password(password, user.password_hash)


@pytest.mark.parametrize("forged_role", ["ADMIN", "OWNER", "admin", "owner"])
def test_register_rejects_client_supplied_role(
    client: TestClient,
    db_session: Session,
    forged_role: str,
):
    email = f"forged-{uuid.uuid4()}@example.com"
    response = client.post(
        "/auth/register",
        json={
            "name": "Forged Role",
            "email": email,
            "password": "secure-password-12",
            "role": forged_role,
        },
    )
    assert response.status_code == 422
    assert db_session.scalar(select(User).where(User.email == email)) is None


def test_register_duplicate_email_rejected(
    client: TestClient,
    db_session: Session,
):
    email = f"dup-{uuid.uuid4()}@example.com"
    first = client.post(
        "/auth/register",
        json={"name": "First", "email": email, "password": "secure-password-12"},
    )
    assert first.status_code == 201
    second = client.post(
        "/auth/register",
        json={"name": "Second", "email": email, "password": "another-password"},
    )
    assert second.status_code == 409
    assert "password" not in second.text.lower() or "password_hash" not in second.text


# ---------------------------------------------------------------------------
# Login / protected routes
# ---------------------------------------------------------------------------


def test_login_then_protected_me_then_logout_is_client_session(
    client: TestClient,
    db_session: Session,
):
    email = f"login-{uuid.uuid4()}@example.com"
    password = "secure-password-12"
    _user(db_session, role="VIEWER", email=email, password=password)

    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert "password" not in login.json()

    me = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "VIEWER"
    assert "password_hash" not in me.json()

    # Stateless logout: without Authorization the next protected call fails.
    denied = client.get("/users/me")
    assert denied.status_code == 401


def test_viewer_cannot_invoke_admin_apis(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    viewer = _user(db_session, role="VIEWER")
    headers = _auth(viewer, auth_settings)
    assert client.get("/admin/users", headers=headers).status_code == 403
    assert client.get("/admin/promotions", headers=headers).status_code == 403
    assert client.get("/admin/summary", headers=headers).status_code == 403
    assert (
        client.patch(
            f"/admin/users/{viewer.id}/role",
            headers=headers,
            json={"role": "ADMIN"},
        ).status_code
        == 403
    )
    db_session.refresh(viewer)
    assert viewer.role == "VIEWER"


# ---------------------------------------------------------------------------
# Admin role assignment
# ---------------------------------------------------------------------------


def test_admin_role_change_takes_effect_on_backend(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    admin = _user(db_session, role="ADMIN")
    viewer = _user(db_session, role="VIEWER")
    resp = client.patch(
        f"/admin/users/{viewer.id}/role",
        headers=_auth(admin, auth_settings),
        json={"role": "OWNER"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "OWNER"
    assert "password_hash" not in resp.json()
    db_session.refresh(viewer)
    assert viewer.role == "OWNER"

    me = client.get("/users/me", headers=_auth(viewer, auth_settings))
    assert me.status_code == 200
    assert me.json()["role"] == "OWNER"


def test_status_patch_still_rejects_role_field(
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


# ---------------------------------------------------------------------------
# Owner promotion
# ---------------------------------------------------------------------------


def test_promotion_approval_rejection_duplicate_and_self_review(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    viewer = _user(db_session, role="VIEWER")
    other_viewer = _user(db_session, role="VIEWER")
    admin = _user(db_session, role="ADMIN")
    viewer_headers = _auth(viewer, auth_settings)
    admin_headers = _auth(admin, auth_settings)

    created = client.post(
        "/promotions/requests",
        headers=viewer_headers,
        json={"justification": "Need upload rights"},
    )
    assert created.status_code == 201
    request_id = created.json()["id"]

    duplicate = client.post(
        "/promotions/requests",
        headers=viewer_headers,
        json={"justification": "Again"},
    )
    assert duplicate.status_code == 409

    # Viewer cannot approve.
    assert (
        client.post(
            f"/admin/promotions/{request_id}/review",
            headers=viewer_headers,
            json={"decision": "APPROVED"},
        ).status_code
        == 403
    )

    rejected = client.post(
        f"/admin/promotions/{request_id}/review",
        headers=admin_headers,
        json={"decision": "REJECTED", "admin_note": "Not yet"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["reviewed_by"] == str(admin.id)
    db_session.refresh(viewer)
    assert viewer.role == "VIEWER"

    # New pending request after rejection.
    again = client.post(
        "/promotions/requests",
        headers=viewer_headers,
        json={"justification": "Retry"},
    )
    assert again.status_code == 201
    approve_id = again.json()["id"]

    approved = client.post(
        f"/admin/promotions/{approve_id}/review",
        headers=admin_headers,
        json={"decision": "APPROVED"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    db_session.refresh(viewer)
    assert viewer.role == "OWNER"

    # Self-review forbidden: craft a pending request owned by the admin actor.
    pending = OwnerPromotionRequest(
        id=uuid.uuid4(),
        requester_id=admin.id,
        status="PENDING",
        justification="edge",
    )
    db_session.add(pending)
    db_session.flush()
    self_review = client.post(
        f"/admin/promotions/{pending.id}/review",
        headers=admin_headers,
        json={"decision": "APPROVED"},
    )
    assert self_review.status_code == 403
    db_session.refresh(pending)
    assert pending.status == "PENDING"

    # Unrelated viewer still cannot list admin promotions.
    assert (
        client.get(
            "/admin/promotions",
            headers=_auth(other_viewer, auth_settings),
        ).status_code
        == 403
    )


def test_promotion_preserves_existing_document_grants(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    viewer = _user(db_session, role="VIEWER")
    admin = _user(db_session, role="ADMIN")

    doc = Document(
        owner_id=owner.id,
        title="Shared Memo",
        category="HR",
        description=None,
        storage_key=f"objects/{uuid.uuid4()}",
        original_filename="memo.docx",
        mime_type=DOCX_MEDIA_TYPE,
        file_size=10,
        sha256_checksum="a" * 64,
    )
    db_session.add(doc)
    db_session.flush()
    grant = DocumentPermission(
        document_id=doc.id,
        user_id=viewer.id,
        permission="READ",
        granted_by=owner.id,
    )
    db_session.add(grant)
    db_session.flush()

    created = client.post(
        "/promotions/requests",
        headers=_auth(viewer, auth_settings),
        json={"justification": "Upload needed"},
    )
    assert created.status_code == 201
    reviewed = client.post(
        f"/admin/promotions/{created.json()['id']}/review",
        headers=_auth(admin, auth_settings),
        json={"decision": "APPROVED"},
    )
    assert reviewed.status_code == 200
    db_session.refresh(viewer)
    assert viewer.role == "OWNER"

    # Grant row still active — promotion must not revoke shared access.
    db_session.refresh(grant)
    assert grant.revoked_at is None
    assert grant.permission == "READ"

    meta = client.get(
        f"/documents/{doc.id}",
        headers=_auth(viewer, auth_settings),
    )
    assert meta.status_code == 200
    assert meta.json()["your_access"] == "READ"
