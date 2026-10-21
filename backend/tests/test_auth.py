"""Authentication and current-user endpoint tests."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from collections.abc import Generator

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_password
from app.core.security.jwt_tokens import ACCESS_TOKEN_TYPE
from app.db.models import User
from app.db.session import get_db, reset_engine
from app.main import app
from app.services.auth_service import GENERIC_AUTH_FAILURE


TEST_JWT_SECRET = "unit-test-jwt-secret-key-32chars-min"


def _auth_settings(**overrides) -> Settings:
    data = {
        "DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/trustvault_db",
        "JWT_SECRET_KEY": TEST_JWT_SECRET,
        "JWT_ALGORITHM": "HS256",
        "JWT_ISSUER": "trustvault",
        "JWT_AUDIENCE": "trustvault-api",
        "ACCESS_TOKEN_EXPIRE_MINUTES": 30,
    }
    data.update(overrides)
    return Settings(**data)


@pytest.fixture()
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = _auth_settings()
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setenv("JWT_ISSUER", "trustvault")
    monkeypatch.setenv("JWT_AUDIENCE", "trustvault-api")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    get_settings.cache_clear()
    reset_engine()
    return settings


@pytest.fixture()
def client(
    db_session: Session,
    auth_settings: Settings,
) -> Generator[TestClient, None, None]:
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


def _create_user(
    session: Session,
    *,
    email: str,
    password: str,
    role: str = "OWNER",
    is_active: bool = True,
) -> User:
    user = User(
        name="Auth Test User",
        email=email.lower(),
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user


def test_login_success(client: TestClient, db_session: Session):
    email = f"owner-{uuid.uuid4()}@example.com"
    password = "correct-horse-battery"
    _create_user(db_session, email=email, password=password)

    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["expires_in"] == 30 * 60
    assert "password" not in payload
    assert "password_hash" not in payload


def test_login_wrong_password(client: TestClient, db_session: Session):
    email = f"owner-{uuid.uuid4()}@example.com"
    _create_user(db_session, email=email, password="correct-password-1")

    response = client.post(
        "/auth/login",
        json={"email": email, "password": "wrong-password-1"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_AUTH_FAILURE


def test_login_unknown_email_generic_error(client: TestClient):
    response = client.post(
        "/auth/login",
        json={
            "email": f"missing-{uuid.uuid4()}@example.com",
            "password": "any-password-12",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_AUTH_FAILURE


def test_login_inactive_account_generic_error(
    client: TestClient,
    db_session: Session,
):
    email = f"inactive-{uuid.uuid4()}@example.com"
    _create_user(
        db_session,
        email=email,
        password="inactive-password",
        is_active=False,
    )
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "inactive-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_AUTH_FAILURE


def test_users_me_with_valid_token(client: TestClient, db_session: Session):
    email = f"me-{uuid.uuid4()}@example.com"
    password = "valid-password-12"
    user = _create_user(db_session, email=email, password=password, role="VIEWER")

    login = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    token = login.json()["access_token"]
    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["email"] == email
    assert body["role"] == "VIEWER"
    assert body["is_active"] is True
    assert "password_hash" not in body
    assert "password" not in body


def test_users_me_missing_token(client: TestClient):
    response = client.get("/users/me")
    assert response.status_code == 401


def test_users_me_malformed_token(client: TestClient):
    response = client.get(
        "/users/me",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert response.status_code == 401


def test_users_me_expired_token(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = _create_user(
        db_session,
        email=f"expired-{uuid.uuid4()}@example.com",
        password="expired-password",
    )
    token, _ = create_access_token(
        subject_user_id=user.id,
        settings=auth_settings,
        expires_delta=timedelta(seconds=-5),
    )
    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_users_me_wrong_secret(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = _create_user(
        db_session,
        email=f"wrong-secret-{uuid.uuid4()}@example.com",
        password="secret-password1",
    )
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "iss": auth_settings.jwt_issuer,
            "aud": auth_settings.jwt_audience,
            "typ": ACCESS_TOKEN_TYPE,
            "jti": str(uuid.uuid4()),
        },
        "different-secret-key-32chars-minimum!!",
        algorithm="HS256",
    )
    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_users_me_wrong_issuer_or_audience(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = _create_user(
        db_session,
        email=f"claims-{uuid.uuid4()}@example.com",
        password="claims-password1",
    )
    now = datetime.now(timezone.utc)
    bad_issuer = jwt.encode(
        {
            "sub": str(user.id),
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "iss": "other-issuer",
            "aud": auth_settings.jwt_audience,
            "typ": ACCESS_TOKEN_TYPE,
            "jti": str(uuid.uuid4()),
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    bad_audience = jwt.encode(
        {
            "sub": str(user.id),
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "iss": auth_settings.jwt_issuer,
            "aud": "other-audience",
            "typ": ACCESS_TOKEN_TYPE,
            "jti": str(uuid.uuid4()),
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )

    assert (
        client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {bad_issuer}"},
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {bad_audience}"},
        ).status_code
        == 401
    )


def test_users_me_deleted_user_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = _create_user(
        db_session,
        email=f"deleted-{uuid.uuid4()}@example.com",
        password="deleted-password",
    )
    token, _ = create_access_token(
        subject_user_id=user.id,
        settings=auth_settings,
    )
    db_session.delete(user)
    db_session.flush()

    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_users_me_deactivated_after_token_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = _create_user(
        db_session,
        email=f"deactivated-{uuid.uuid4()}@example.com",
        password="deactivated-pass",
    )
    token, _ = create_access_token(
        subject_user_id=user.id,
        settings=auth_settings,
    )
    user.is_active = False
    db_session.flush()

    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_password_stored_as_hash_not_plaintext(db_session: Session):
    password = "plaintext-should-not-persist"
    user = _create_user(
        db_session,
        email=f"hash-{uuid.uuid4()}@example.com",
        password=password,
    )
    assert user.password_hash != password
    assert user.password_hash.startswith("$argon2")


def test_auth_failures_do_not_log_secrets(
    client: TestClient,
    db_session: Session,
    caplog: pytest.LogCaptureFixture,
):
    email = f"log-{uuid.uuid4()}@example.com"
    password = "visible-only-in-test-input"
    _create_user(db_session, email=email, password=password)

    with caplog.at_level(logging.INFO):
        client.post(
            "/auth/login",
            json={"email": email, "password": "wrong-password-value"},
        )
        login = client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )

    token = login.json()["access_token"]
    combined = " | ".join(record.getMessage() for record in caplog.records)
    assert password not in combined
    assert "wrong-password-value" not in combined
    assert token not in combined
    assert "password_hash" not in combined
