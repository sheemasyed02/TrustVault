"""Argon2id password hashing via pwdlib."""

from __future__ import annotations

from pwdlib import PasswordHash

_password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password is required")
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    try:
        return _password_hasher.verify(password, password_hash)
    except Exception:
        # Invalid hash format or library error — treat as failed verification.
        return False
