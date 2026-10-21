"""Signed JWT access tokens.

Logout for a pure JWT access token does not revoke an already-issued token by
itself unless a separate revocation store is implemented (not present yet).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import Settings, get_settings

ALLOWED_ALGORITHMS = frozenset({"HS256"})
ACCESS_TOKEN_TYPE = "access"


class AccessTokenError(Exception):
    """Raised when an access token is missing, malformed, or invalid."""


def _require_auth_settings(settings: Settings) -> Settings:
    secret = settings.resolved_jwt_secret
    if settings.jwt_algorithm not in ALLOWED_ALGORITHMS:
        raise AccessTokenError("Unsupported JWT algorithm configuration")
    if not secret:
        raise AccessTokenError("JWT signing secret is not configured")
    return settings


def create_access_token(
    *,
    subject_user_id: uuid.UUID,
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, datetime]:
    """Return (token, expires_at_utc). Role is intentionally omitted from claims."""
    resolved = _require_auth_settings(settings or get_settings())
    now = datetime.now(timezone.utc)
    expires_at = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=resolved.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": str(subject_user_id),
        "iat": now,
        "exp": expires_at,
        "iss": resolved.jwt_issuer,
        "aud": resolved.jwt_audience,
        "typ": ACCESS_TOKEN_TYPE,
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(
        payload,
        resolved.resolved_jwt_secret,
        algorithm=resolved.jwt_algorithm,
    )
    return token, expires_at


def decode_access_token(
    token: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Validate signature, expiry, issuer, audience, and token type."""
    if not token or not token.strip():
        raise AccessTokenError("Missing access token")

    resolved = _require_auth_settings(settings or get_settings())
    algorithm = resolved.jwt_algorithm
    if algorithm not in ALLOWED_ALGORITHMS:
        raise AccessTokenError("Unsupported JWT algorithm configuration")

    try:
        payload = jwt.decode(
            token,
            resolved.resolved_jwt_secret,
            algorithms=[algorithm],
            audience=resolved.jwt_audience,
            issuer=resolved.jwt_issuer,
            options={
                "require": ["sub", "exp", "iat", "iss", "aud", "typ"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )
    except jwt.PyJWTError as exc:
        raise AccessTokenError("Invalid access token") from exc

    if payload.get("typ") != ACCESS_TOKEN_TYPE:
        raise AccessTokenError("Invalid access token")

    subject = payload.get("sub")
    if not subject or not isinstance(subject, str):
        raise AccessTokenError("Invalid access token")

    try:
        uuid.UUID(subject)
    except ValueError as exc:
        raise AccessTokenError("Invalid access token") from exc

    return payload
