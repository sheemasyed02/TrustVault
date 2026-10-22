"""Self-service profile and password change — own account only."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.db.session import get_db, reset_engine
from app.main import app

TEST_JWT_SECRET = "profile-password-jwt-secret-key-32c"
OLD_PASSWORD = "old-password-12"
NEW_PASSWORD = "new-password-99"


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
def _noop_committed_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid DENIED audit sessions locking against the test transaction."""

    def _noop(**_kwargs):
        return None

    monkeypatch.setattr("app.api.users.append_audit_event_committed", _noop)
    monkeypatch.setattr("app.api.auth.append_audit_event_committed", _noop)


@pytest.fixture()
def client(
    db_session: Session,
    auth_settings: Settings,
    _noop_committed_audit: None,
) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: auth_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _user(session: Session, *, role: str, password: str = OLD_PASSWORD) -> User:
    user = User(
        name=f"{role} Profile",
        email=f"{role.lower()}-{uuid.uuid4()}@example.com",
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _auth(user: User, settings: Settings) -> dict[str, str]:
    token, _ = create_access_token(subject_user_id=user.id, settings=settings)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("role", ["ADMIN", "OWNER", "VIEWER"])
def test_each_role_can_read_own_profile(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    role: str,
):
    user = _user(db_session, role=role)
    resp = client.get("/users/me", headers=_auth(user, auth_settings))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(user.id)
    assert body["email"] == user.email
    assert body["role"] == role
    assert body["is_active"] is True
    assert "created_at" in body
    assert "password" not in body
    assert "password_hash" not in body


def test_cannot_patch_another_user_via_me_endpoint(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    alice = _user(db_session, role="OWNER")
    bob = _user(db_session, role="VIEWER")
    # /users/me always targets the token subject — no user_id path to hijack.
    resp = client.patch(
        "/users/me",
        headers=_auth(alice, auth_settings),
        json={"name": "Alice Updated"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == str(alice.id)
    assert resp.json()["name"] == "Alice Updated"
    db_session.refresh(bob)
    assert bob.name.startswith("VIEWER")


def test_profile_update_rejects_role_email_status(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = _user(db_session, role="VIEWER")
    headers = _auth(user, auth_settings)
    forbidden = client.patch(
        "/users/me",
        headers=headers,
        json={
            "name": "Still Viewer",
            "role": "ADMIN",
            "email": "hijack@example.com",
            "is_active": False,
        },
    )
    assert forbidden.status_code == 422
    db_session.refresh(user)
    assert user.role == "VIEWER"
    assert user.is_active is True
    assert not user.email.startswith("hijack")

    ok = client.patch(
        "/users/me",
        headers=headers,
        json={"name": "Renamed Viewer"},
    )
    assert ok.status_code == 200
    assert ok.json()["role"] == "VIEWER"
    assert ok.json()["name"] == "Renamed Viewer"


def test_password_change_success_and_old_password_fails(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = _user(db_session, role="OWNER")
    headers = _auth(user, auth_settings)
    resp = client.post(
        "/users/me/password",
        headers=headers,
        json={
            "current_password": OLD_PASSWORD,
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "message" in body
    assert "password" not in body
    assert "password_hash" not in body

    db_session.refresh(user)
    assert verify_password(NEW_PASSWORD, user.password_hash)
    assert not verify_password(OLD_PASSWORD, user.password_hash)
    assert user.password_hash != NEW_PASSWORD
    assert user.password_hash != OLD_PASSWORD

    old_login = client.post(
        "/auth/login",
        json={"email": user.email, "password": OLD_PASSWORD},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/auth/login",
        json={"email": user.email, "password": NEW_PASSWORD},
    )
    assert new_login.status_code == 200
    assert "access_token" in new_login.json()


def test_incorrect_current_password_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = _user(db_session, role="VIEWER")
    previous_hash = user.password_hash
    resp = client.post(
        "/users/me/password",
        headers=_auth(user, auth_settings),
        json={
            "current_password": "wrong-password-99",
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
    )
    assert resp.status_code == 401
    db_session.refresh(user)
    assert user.password_hash == previous_hash


def test_mismatched_new_passwords_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = _user(db_session, role="ADMIN")
    previous_hash = user.password_hash
    resp = client.post(
        "/users/me/password",
        headers=_auth(user, auth_settings),
        json={
            "current_password": OLD_PASSWORD,
            "new_password": NEW_PASSWORD,
            "confirm_password": "different-password-1",
        },
    )
    assert resp.status_code == 422
    db_session.refresh(user)
    assert user.password_hash == previous_hash


def test_unauthenticated_profile_and_password_denied(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    del auth_settings
    user = _user(db_session, role="VIEWER")
    assert client.get("/users/me").status_code == 401
    assert (
        client.patch("/users/me", json={"name": "Nope"}).status_code == 401
    )
    assert (
        client.post(
            "/users/me/password",
            json={
                "current_password": OLD_PASSWORD,
                "new_password": NEW_PASSWORD,
                "confirm_password": NEW_PASSWORD,
            },
        ).status_code
        == 401
    )
    db_session.refresh(user)
    assert verify_password(OLD_PASSWORD, user.password_hash)
