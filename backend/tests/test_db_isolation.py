"""Ensure pytest sessions cannot leak users into the shared development database."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import User
from app.db.session import get_session_factory


def test_session_commit_only_releases_savepoint_not_outer_transaction(
    db_session: Session,
):
    """Endpoint-style session.commit() must not be visible on another connection."""
    email = f"nosurvive-{uuid.uuid4()}@example.com"
    db_session.add(
        User(
            name="Leak Probe Security",
            email=email,
            password_hash=hash_password("isolation-check-password-12"),
            role="VIEWER",
            is_active=True,
        )
    )
    db_session.flush()
    # Simulate application code that commits the request session.
    db_session.commit()

    assert db_session.scalar(select(User).where(User.email == email)) is not None

    outsider = get_session_factory()()
    try:
        leaked = outsider.scalar(select(User).where(User.email == email))
        assert leaked is None, (
            "Test user was visible outside the fixture transaction — "
            "pytest isolation is broken and will pollute the users table."
        )
    finally:
        outsider.close()
