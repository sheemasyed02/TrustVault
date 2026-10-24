"""Forgot-password and reset-password HTTP API tests (Brevo mocked)."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import hash_password, verify_password
from app.db.models import PasswordResetToken, User
from app.db.session import get_db, reset_engine
from app.main import app
from app.services.brevo_email import EmailDeliveryError
from app.services.password_reset_rate_limit import reset_password_reset_rate_limiter
from app.services.password_reset_service import GENERIC_FORGOT_PASSWORD_MESSAGE
from app.services.password_reset_tokens import (
    create_password_reset_token,
    hash_reset_token,
)

TEST_JWT_SECRET = "password-reset-api-jwt-secret-key-32c"
OLD_PASSWORD = "old-password-12"
NEW_PASSWORD = "new-password-99"


def _settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/trustvault_db",
        "JWT_SECRET_KEY": TEST_JWT_SECRET,
        "JWT_ALGORITHM": "HS256",
        "JWT_ISSUER": "trustvault",
        "JWT_AUDIENCE": "trustvault-api",
        "ACCESS_TOKEN_EXPIRE_MINUTES": 30,
        "FRONTEND_BASE_URL": "http://localhost:3000",
        "PASSWORD_RESET_TOKEN_EXPIRE_MINUTES": 30,
        "BREVO_API_KEY": "test-brevo-key",
        "BREVO_SENDER_EMAIL": "noreply@trustvault.example",
        "BREVO_SENDER_NAME": "TrustVault",
        "PASSWORD_RESET_RATE_LIMIT_IP_MAX": 100,
        "PASSWORD_RESET_RATE_LIMIT_EMAIL_MAX": 100,
        "PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS": 3600,
    }
    data.update(overrides)
    return Settings(**data)


@pytest.fixture()
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = _settings()
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    get_settings.cache_clear()
    reset_engine()
    reset_password_reset_rate_limiter()
    return settings


@pytest.fixture()
def _noop_committed_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.auth.append_audit_event_committed", lambda **_k: None)


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
    reset_password_reset_rate_limiter()


def _user(
    session: Session,
    *,
    role: str = "VIEWER",
    email: str | None = None,
    password: str = OLD_PASSWORD,
    is_active: bool = True,
) -> User:
    user = User(
        name=f"{role} Reset",
        email=email or f"{role.lower()}-{uuid.uuid4()}@example.com",
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user


def _count_tokens(session: Session, user_id: uuid.UUID) -> int:
    return len(
        list(
            session.scalars(
                select(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
            )
        )
    )


def test_forgot_password_registered_creates_token_and_calls_brevo(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
):
    user = _user(db_session, role="OWNER")
    send_mock = MagicMock()
    monkeypatch.setattr(
        "app.services.password_reset_service.send_password_reset_email",
        send_mock,
    )

    resp = client.post("/auth/forgot-password", json={"email": user.email})
    assert resp.status_code == 200
    assert resp.json()["message"] == GENERIC_FORGOT_PASSWORD_MESSAGE
    assert _count_tokens(db_session, user.id) == 1
    send_mock.assert_called_once()
    kwargs = send_mock.call_args.kwargs
    assert kwargs["to_email"] == user.email
    assert kwargs["raw_token"]
    assert kwargs["raw_token"] not in resp.text


def test_forgot_password_unregistered_no_token_no_brevo(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    send_mock = MagicMock()
    monkeypatch.setattr(
        "app.services.password_reset_service.send_password_reset_email",
        send_mock,
    )
    email = f"missing-{uuid.uuid4()}@example.com"

    resp = client.post("/auth/forgot-password", json={"email": email})
    assert resp.status_code == 200
    assert resp.json()["message"] == GENERIC_FORGOT_PASSWORD_MESSAGE
    send_mock.assert_not_called()
    tokens = list(db_session.scalars(select(PasswordResetToken)))
    assert tokens == []


def test_forgot_password_inactive_user_treated_like_unknown(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    user = _user(db_session, is_active=False)
    send_mock = MagicMock()
    monkeypatch.setattr(
        "app.services.password_reset_service.send_password_reset_email",
        send_mock,
    )

    resp = client.post("/auth/forgot-password", json={"email": user.email})
    assert resp.status_code == 200
    assert resp.json()["message"] == GENERIC_FORGOT_PASSWORD_MESSAGE
    send_mock.assert_not_called()
    assert _count_tokens(db_session, user.id) == 0


def test_forgot_password_same_public_shape_for_known_and_unknown(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    user = _user(db_session)
    monkeypatch.setattr(
        "app.services.password_reset_service.send_password_reset_email",
        MagicMock(),
    )
    known = client.post("/auth/forgot-password", json={"email": user.email})
    unknown = client.post(
        "/auth/forgot-password",
        json={"email": f"ghost-{uuid.uuid4()}@example.com"},
    )
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert set(known.json().keys()) == {"message"}


def test_forgot_password_invalid_email_rejected(client: TestClient):
    resp = client.post("/auth/forgot-password", json={"email": "not-an-email"})
    assert resp.status_code == 422


def test_forgot_password_brevo_failure_does_not_leak_account(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    user = _user(db_session)
    monkeypatch.setattr(
        "app.services.password_reset_service.send_password_reset_email",
        MagicMock(
            side_effect=EmailDeliveryError(
                "Unable to send password reset email",
                reason_code="BREVO_REJECTED",
                status_code=401,
            )
        ),
    )
    resp = client.post("/auth/forgot-password", json={"email": user.email})
    assert resp.status_code == 503
    detail = resp.json()["detail"].lower()
    assert "unable to process" in detail
    assert user.email not in resp.text
    assert "registered" not in detail
    assert "not found" not in detail


def test_forgot_password_rate_limit_by_email(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    reset_password_reset_rate_limiter()
    limited = _settings(
        PASSWORD_RESET_RATE_LIMIT_EMAIL_MAX=2,
        PASSWORD_RESET_RATE_LIMIT_IP_MAX=100,
    )
    app.dependency_overrides[get_settings] = lambda: limited
    monkeypatch.setattr(
        "app.services.password_reset_service.send_password_reset_email",
        MagicMock(),
    )
    email = f"rate-{uuid.uuid4()}@example.com"
    _user(db_session, email=email)

    assert client.post("/auth/forgot-password", json={"email": email}).status_code == 200
    assert client.post("/auth/forgot-password", json={"email": email}).status_code == 200
    third = client.post("/auth/forgot-password", json={"email": email})
    assert third.status_code == 429
    assert "too many" in third.json()["detail"].lower()


def test_reset_password_success_changes_hash_and_consumes_token(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = _user(db_session)
    old_hash = user.password_hash
    issued = create_password_reset_token(
        db_session, user=user, settings=auth_settings
    )

    resp = client.post(
        "/auth/reset-password",
        json={
            "token": issued.raw_token,
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
    )
    assert resp.status_code == 200
    assert "Password updated" in resp.json()["message"]

    db_session.refresh(user)
    db_session.refresh(issued.record)
    assert user.password_hash != old_hash
    assert verify_password(NEW_PASSWORD, user.password_hash)
    assert issued.record.used_at is not None

    login = client.post(
        "/auth/login",
        json={"email": user.email, "password": NEW_PASSWORD},
    )
    assert login.status_code == 200
    assert login.json()["access_token"]


def test_reset_password_rejects_invalid_expired_and_used_tokens(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = _user(db_session)
    payload = {
        "new_password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD,
    }

    invalid = client.post(
        "/auth/reset-password",
        json={"token": "not-a-real-token-value", **payload},
    )
    assert invalid.status_code == 400
    assert "invalid or has expired" in invalid.json()["detail"].lower()

    issued = create_password_reset_token(
        db_session, user=user, settings=auth_settings
    )
    issued.record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.flush()
    expired = client.post(
        "/auth/reset-password",
        json={"token": issued.raw_token, **payload},
    )
    assert expired.status_code == 400

    fresh = create_password_reset_token(
        db_session, user=user, settings=auth_settings
    )
    first = client.post(
        "/auth/reset-password",
        json={"token": fresh.raw_token, **payload},
    )
    assert first.status_code == 200
    reused = client.post(
        "/auth/reset-password",
        json={
            "token": fresh.raw_token,
            "new_password": "another-password-1",
            "confirm_password": "another-password-1",
        },
    )
    assert reused.status_code == 400


def test_reset_password_rejects_mismatch_and_short_password(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = _user(db_session)
    issued = create_password_reset_token(
        db_session, user=user, settings=auth_settings
    )

    mismatch = client.post(
        "/auth/reset-password",
        json={
            "token": issued.raw_token,
            "new_password": NEW_PASSWORD,
            "confirm_password": "different-password",
        },
    )
    assert mismatch.status_code == 422
    assert "match" in mismatch.json()["detail"].lower()

    short = client.post(
        "/auth/reset-password",
        json={
            "token": issued.raw_token,
            "new_password": "short",
            "confirm_password": "short",
        },
    )
    # Schema min_length=10 → 422 validation, or service policy.
    assert short.status_code == 422

    db_session.refresh(issued.record)
    assert issued.record.used_at is None
    assert hash_reset_token(issued.raw_token) == issued.record.token_hash


@pytest.mark.parametrize("role", ["ADMIN", "OWNER", "VIEWER"])
def test_existing_login_still_works_for_roles(
    client: TestClient,
    db_session: Session,
    role: str,
):
    password = "role-login-pass-12"
    user = _user(db_session, role=role, password=password)
    resp = client.post(
        "/auth/login",
        json={"email": user.email, "password": password},
    )
    assert resp.status_code == 200
    me = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {resp.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["role"] == role


def test_admin_can_use_self_service_forgot_password(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """No ADMIN exclusion policy exists; admins remain eligible like other roles."""
    admin = _user(db_session, role="ADMIN")
    send_mock = MagicMock()
    monkeypatch.setattr(
        "app.services.password_reset_service.send_password_reset_email",
        send_mock,
    )
    resp = client.post("/auth/forgot-password", json={"email": admin.email})
    assert resp.status_code == 200
    send_mock.assert_called_once()
    assert _count_tokens(db_session, admin.id) == 1


def test_reset_does_not_echo_token_or_password(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = _user(db_session)
    issued = create_password_reset_token(
        db_session, user=user, settings=auth_settings
    )
    resp = client.post(
        "/auth/reset-password",
        json={
            "token": issued.raw_token,
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
    )
    assert resp.status_code == 200
    body = resp.text
    assert issued.raw_token not in body
    assert NEW_PASSWORD not in body
    assert "password_hash" not in body
