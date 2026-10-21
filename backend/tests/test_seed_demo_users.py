"""Demo seed command tests — development only."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from sqlalchemy import delete

from app.cli.seed_demo_users import (
    DEMO_ACCOUNTS,
    SeedConflictError,
    seed_demo_users,
)
from app.core.security import hash_password, verify_password
from app.db.models import AuditEvent, Document, DocumentPermission, User
from app.services.auth_service import normalize_email

DEMO_EMAILS = [normalize_email(account.email) for account in DEMO_ACCOUNTS]


def _clear_demo_users(session: Session) -> None:
    """Remove demo emails inside the test transaction (rolled back afterward).

    Demo OWNER accounts may own documents from manual UI testing against the
    shared local database; clear dependent rows before deleting users.
    """
    demo_ids = select(User.id).where(User.email.in_(DEMO_EMAILS)).scalar_subquery()
    demo_doc_ids = (
        select(Document.id).where(Document.owner_id.in_(demo_ids)).scalar_subquery()
    )
    session.execute(
        delete(DocumentPermission).where(
            DocumentPermission.document_id.in_(demo_doc_ids)
            | DocumentPermission.user_id.in_(demo_ids)
            | DocumentPermission.granted_by.in_(demo_ids)
        )
    )
    session.execute(
        delete(AuditEvent).where(
            AuditEvent.document_id.in_(demo_doc_ids)
            | AuditEvent.actor_id.in_(demo_ids)
            | AuditEvent.target_user_id.in_(demo_ids)
        )
    )
    session.execute(delete(Document).where(Document.owner_id.in_(demo_ids)))
    session.execute(delete(User).where(User.email.in_(DEMO_EMAILS)))
    session.flush()


@pytest.fixture()
def demo_passwords(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    passwords = {
        "DEMO_ADMIN_PASSWORD": f"admin-pass-{uuid.uuid4()}-xx",
        "DEMO_OWNER_PASSWORD": f"owner-pass-{uuid.uuid4()}-xx",
        "DEMO_VIEWER_PASSWORD": f"viewer-pass-{uuid.uuid4()}-xx",
    }
    for key, value in passwords.items():
        monkeypatch.setenv(key, value)
    return passwords


def test_seed_creates_required_roles(
    db_session: Session,
    demo_passwords: dict[str, str],
):
    _clear_demo_users(db_session)
    results = seed_demo_users(db_session)
    db_session.flush()

    assert set(results.values()) == {"created"}
    for account in DEMO_ACCOUNTS:
        user = db_session.scalar(
            select(User).where(User.email == normalize_email(account.email))
        )
        assert user is not None
        assert user.role == account.role
        assert user.is_active is True
        assert user.password_hash.startswith("$argon2")
        assert verify_password(
            demo_passwords[account.password_env],
            user.password_hash,
        )


def test_seed_is_idempotent_and_does_not_reset_password_or_role(
    db_session: Session,
    demo_passwords: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    _clear_demo_users(db_session)
    first = seed_demo_users(db_session)
    db_session.flush()
    assert set(first.values()) == {"created"}

    admin = db_session.scalar(
        select(User).where(User.email == "snovasys@trustvault.demo")
    )
    assert admin is not None
    original_hash = admin.password_hash
    original_role = admin.role

    # Different passwords on second run must not rewrite the stored hash.
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", f"changed-admin-{uuid.uuid4()}-yy")
    monkeypatch.setenv("DEMO_OWNER_PASSWORD", f"changed-owner-{uuid.uuid4()}-yy")
    monkeypatch.setenv("DEMO_VIEWER_PASSWORD", f"changed-viewer-{uuid.uuid4()}-yy")

    second = seed_demo_users(db_session)
    db_session.flush()
    assert set(second.values()) == {"exists"}

    db_session.refresh(admin)
    assert admin.password_hash == original_hash
    assert admin.role == original_role
    assert verify_password(demo_passwords["DEMO_ADMIN_PASSWORD"], admin.password_hash)


def test_seed_conflict_on_unexpected_role(
    db_session: Session,
    demo_passwords: dict[str, str],
):
    _clear_demo_users(db_session)
    db_session.add(
        User(
            name="Conflict",
            email="snovasys@trustvault.demo",
            password_hash=hash_password(demo_passwords["DEMO_ADMIN_PASSWORD"]),
            role="VIEWER",
            is_active=True,
        )
    )
    db_session.flush()

    with pytest.raises(SeedConflictError, match="expected ADMIN"):
        seed_demo_users(db_session)


def test_seed_requires_password_env(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("DEMO_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_OWNER_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_VIEWER_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="DEMO_ADMIN_PASSWORD"):
        seed_demo_users(db_session)
