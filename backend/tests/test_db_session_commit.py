"""Regression: request sessions must commit or uploads vanish after HTTP 201."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database_url import DatabaseURLError
from app.core.security import hash_password
from app.db.models import User
from app.db.session import get_db, get_session_factory, reset_engine


@pytest.fixture()
def isolated_engine() -> Generator[None, None, None]:
    get_settings.cache_clear()
    reset_engine()
    try:
        get_settings()
    except (DatabaseURLError, Exception) as exc:
        pytest.skip(f"DATABASE_URL is not usable: {exc.__class__.__name__}")
    yield
    reset_engine()
    get_settings.cache_clear()


def test_get_db_commits_successful_work(isolated_engine: None) -> None:
    email = "commit-persist@example.com"
    gen = get_db()
    session = next(gen)
    try:
        session.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
        session.flush()
        user = User(
            name="Commit Persist",
            email=email,
            password_hash=hash_password("commit-persist-password-12"),
            role="OWNER",
            is_active=True,
        )
        session.add(user)
        session.flush()
        user_id = user.id
    finally:
        # Successful generator completion → commit inside get_db.
        try:
            next(gen)
        except StopIteration:
            pass

    verify = get_session_factory()()
    try:
        found = verify.scalar(select(User).where(User.id == user_id))
        assert found is not None
        assert found.email == email
        verify.execute(text("DELETE FROM users WHERE id = :id"), {"id": str(user_id)})
        verify.commit()
    finally:
        verify.close()


def test_get_db_rolls_back_on_error(isolated_engine: None) -> None:
    email = "commit-rollback@example.com"
    gen = get_db()
    session = next(gen)
    user_id = None
    try:
        session.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
        session.flush()
        user = User(
            name="Commit Rollback",
            email=email,
            password_hash=hash_password("commit-rollback-password-12"),
            role="OWNER",
            is_active=True,
        )
        session.add(user)
        session.flush()
        user_id = user.id
        gen.throw(RuntimeError("force rollback"))
    except RuntimeError:
        pass

    assert user_id is not None
    verify = get_session_factory()()
    try:
        found = verify.scalar(select(User).where(User.id == user_id))
        assert found is None
    finally:
        verify.close()
