"""Unit tests for password-reset tokens and Brevo email foundation.

External Brevo HTTP calls are mocked — these tests never send real email.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password
from app.db.models import PasswordResetToken, User
from app.services.brevo_email import (
    BREVO_SMTP_EMAIL_URL,
    EmailConfigurationError,
    EmailDeliveryError,
    build_password_reset_email_content,
    build_password_reset_url,
    load_brevo_email_config,
    send_password_reset_email,
)
from app.services.password_reset_tokens import (
    PasswordResetTokenError,
    consume_password_reset_token,
    create_password_reset_token,
    generate_raw_reset_token,
    get_valid_password_reset_token,
    hash_reset_token,
)


def _settings(**overrides: object) -> Settings:
    base = {
        "DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/trustvault_db",
        "JWT_SECRET_KEY": "password-reset-test-jwt-secret-key-32c",
        "FRONTEND_BASE_URL": "http://localhost:3000",
        "PASSWORD_RESET_TOKEN_EXPIRE_MINUTES": 30,
        "BREVO_API_KEY": "test-brevo-key",
        "BREVO_SENDER_EMAIL": "noreply@trustvault.example",
        "BREVO_SENDER_NAME": "TrustVault",
    }
    base.update(overrides)
    return Settings(**base)


def _user(session: Session) -> User:
    user = User(
        name="Reset User",
        email=f"reset-{uuid.uuid4()}@example.com",
        password_hash=hash_password("reset-password-12"),
        role="VIEWER",
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


# ---------------------------------------------------------------------------
# Token generation / hashing
# ---------------------------------------------------------------------------


def test_generate_raw_reset_token_has_sufficient_entropy() -> None:
    token = generate_raw_reset_token()
    # token_urlsafe(32) yields ~43 chars; ensure we never fall below 32 bytes entropy API.
    assert isinstance(token, str)
    assert len(token) >= 43
    assert generate_raw_reset_token() != generate_raw_reset_token()


def test_generate_raw_reset_token_rejects_weak_entropy() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        generate_raw_reset_token(nbytes=16)


def test_hash_reset_token_is_sha256_hex_and_stable() -> None:
    raw = "example-raw-token-value"
    digest = hash_reset_token(raw)
    assert digest == hash_reset_token(raw)
    assert len(digest) == 64
    assert digest != raw
    assert all(c in "0123456789abcdef" for c in digest)


def test_hash_reset_token_rejects_empty() -> None:
    with pytest.raises(ValueError):
        hash_reset_token("")


# ---------------------------------------------------------------------------
# Persistence: create / expire / single-use
# ---------------------------------------------------------------------------


def test_create_stores_hash_not_raw_token(db_session: Session) -> None:
    user = _user(db_session)
    settings = _settings()
    issued = create_password_reset_token(db_session, user=user, settings=settings)

    assert issued.raw_token
    assert issued.record.token_hash == hash_reset_token(issued.raw_token)
    assert issued.raw_token not in (issued.record.token_hash or "")
    assert issued.record.used_at is None
    assert issued.record.user_id == user.id
    assert issued.record.expires_at > datetime.now(timezone.utc)


def test_valid_token_lookup_and_expiration(db_session: Session) -> None:
    user = _user(db_session)
    settings = _settings(PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=30)
    issued = create_password_reset_token(db_session, user=user, settings=settings)

    found = get_valid_password_reset_token(db_session, raw_token=issued.raw_token)
    assert found is not None
    assert found.id == issued.record.id

    past = datetime.now(timezone.utc) + timedelta(minutes=31)
    assert (
        get_valid_password_reset_token(
            db_session, raw_token=issued.raw_token, now=past
        )
        is None
    )


def test_consume_is_single_use(db_session: Session) -> None:
    user = _user(db_session)
    settings = _settings()
    issued = create_password_reset_token(db_session, user=user, settings=settings)

    consume_password_reset_token(db_session, record=issued.record)
    assert issued.record.used_at is not None

    assert (
        get_valid_password_reset_token(db_session, raw_token=issued.raw_token)
        is None
    )

    with pytest.raises(PasswordResetTokenError) as exc_info:
        consume_password_reset_token(db_session, record=issued.record)
    assert exc_info.value.reason_code == "TOKEN_ALREADY_USED"


def test_consume_rejects_expired_token(db_session: Session) -> None:
    user = _user(db_session)
    settings = _settings(PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=1)
    issued = create_password_reset_token(db_session, user=user, settings=settings)

    past = datetime.now(timezone.utc) + timedelta(minutes=5)
    with pytest.raises(PasswordResetTokenError) as exc_info:
        consume_password_reset_token(
            db_session, record=issued.record, now=past
        )
    assert exc_info.value.reason_code == "TOKEN_EXPIRED"
    assert issued.record.used_at is None


def test_unknown_raw_token_is_invalid(db_session: Session) -> None:
    assert get_valid_password_reset_token(db_session, raw_token="not-a-real-token") is None


# ---------------------------------------------------------------------------
# Brevo configuration + delivery (mocked HTTP)
# ---------------------------------------------------------------------------


def test_load_brevo_config_requires_env() -> None:
    settings = _settings(
        BREVO_API_KEY=None,
        BREVO_SENDER_EMAIL="",
        FRONTEND_BASE_URL=None,
    )
    with pytest.raises(EmailConfigurationError) as exc_info:
        load_brevo_email_config(settings)
    assert "BREVO_API_KEY" in exc_info.value.missing
    assert "BREVO_SENDER_EMAIL" in exc_info.value.missing
    assert "FRONTEND_BASE_URL" in exc_info.value.missing
    assert "BREVO_SENDER_NAME" not in exc_info.value.missing


def test_load_brevo_config_rejects_non_http_frontend() -> None:
    settings = _settings(FRONTEND_BASE_URL="localhost:3000")
    with pytest.raises(EmailConfigurationError, match="FRONTEND_BASE_URL"):
        load_brevo_email_config(settings)


def test_build_password_reset_url_puts_token_only_in_query() -> None:
    url = build_password_reset_url(
        frontend_base_url="http://localhost:3000/",
        raw_token="abc+/=",
    )
    assert url.startswith("http://localhost:3000/reset-password?token=")
    assert "abc" in url
    # Plus and slash must be percent-encoded in the query value.
    assert "abc%2B%2F%3D" in url
    assert "/reset-password?token=" in url


def test_email_content_is_branded_and_includes_link() -> None:
    subject, text_body, html_body = build_password_reset_email_content(
        recipient_name="Alex",
        reset_url="http://localhost:3000/reset-password?token=secret",
        expire_minutes=30,
    )
    assert "TrustVault" in subject
    assert "Alex" in text_body
    assert "http://localhost:3000/reset-password?token=secret" in text_body
    assert "30 minutes" in text_body
    assert "ignore this email" in text_body.lower()
    assert "TrustVault" in html_body
    assert "Reset Password" in html_body
    assert "http://localhost:3000/reset-password?token=secret" in html_body
    # TrustVault product palette only (no legacy teal / grey UI colours).
    for colour in (
        "#FAF8F5",
        "#FFFFFF",
        "#8B78A6",
        "#6F5A88",
        "#30283B",
        "#F8F5FA",
        "#342B3D",
        "#817986",
        "#E8E0EF",
        "#C5A568",
        "#F1ECF6",
    ):
        assert colour in html_body
    assert "#0f766e" not in html_body.lower()
    assert "expires in <strong style=\"color:#342B3D;\">30 minutes</strong>" in html_body
    # No invented remote logo URL / local filesystem paths.
    assert "src=" not in html_body.lower()
    assert "file://" not in html_body.lower()


def test_send_password_reset_email_success_mocked() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key_header"] = request.headers.get("api-key")
        captured["content_type"] = request.headers.get("content-type")
        captured["body"] = request.read()
        return httpx.Response(201, json={"messageId": "msg-1"})

    transport = httpx.MockTransport(handler)
    settings = _settings()
    with httpx.Client(transport=transport) as client:
        send_password_reset_email(
            settings,
            to_email="viewer@example.com",
            to_name="Viewer",
            raw_token="unit-test-raw-token",
            client=client,
        )

    assert captured["url"] == BREVO_SMTP_EMAIL_URL
    assert captured["api_key_header"] == "test-brevo-key"
    assert captured["content_type"] == "application/json"
    body = captured["body"]
    assert isinstance(body, bytes)
    assert b"unit-test-raw-token" in body
    assert b"viewer@example.com" in body
    assert b"TrustVault" in body


def test_send_password_reset_email_brevo_rejection() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text='{"message":"Key not found"}')

    transport = httpx.MockTransport(handler)
    settings = _settings()
    with httpx.Client(transport=transport) as client:
        with pytest.raises(EmailDeliveryError) as exc_info:
            send_password_reset_email(
                settings,
                to_email="viewer@example.com",
                to_name="Viewer",
                raw_token="unit-test-raw-token",
                client=client,
            )
    assert exc_info.value.reason_code == "BREVO_REJECTED"
    assert exc_info.value.status_code == 401


def test_send_password_reset_email_network_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    settings = _settings()
    with httpx.Client(transport=transport) as client:
        with pytest.raises(EmailDeliveryError) as exc_info:
            send_password_reset_email(
                settings,
                to_email="viewer@example.com",
                to_name="Viewer",
                raw_token="unit-test-raw-token",
                client=client,
            )
    assert exc_info.value.reason_code == "BREVO_NETWORK_ERROR"


def test_send_refuses_when_config_missing() -> None:
    settings = _settings(BREVO_API_KEY=None)
    with pytest.raises(EmailConfigurationError):
        send_password_reset_email(
            settings,
            to_email="viewer@example.com",
            to_name="Viewer",
            raw_token="unit-test-raw-token",
        )


def test_password_reset_token_model_indexes_present() -> None:
    """Sanity: model metadata exposes expected uniqueness/index names."""
    table = PasswordResetToken.__table__
    constraint_names = {c.name for c in table.constraints if c.name}
    index_names = {idx.name for idx in table.indexes}
    assert "uq_password_reset_tokens_token_hash" in constraint_names
    assert "ix_password_reset_tokens_user_id" in index_names
    assert "ix_password_reset_tokens_expires_at" in index_names
