"""Integration tests for schema connectivity, constraints, and relationships."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Document, DocumentPermission, User
from app.db.session import check_database_connection, get_engine, reset_engine
from app.core.config import get_settings


def test_database_connectivity():
    get_settings.cache_clear()
    reset_engine()
    assert check_database_connection() is True


def test_expected_tables_exist():
    get_settings.cache_clear()
    reset_engine()
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN
                      ('users', 'documents', 'document_permissions', 'audit_events')
                ORDER BY table_name
                """
            )
        ).fetchall()
    assert [row[0] for row in rows] == [
        "audit_events",
        "document_permissions",
        "documents",
        "users",
    ]


def _make_user(session: Session, *, email: str, role: str = "OWNER") -> User:
    user = User(
        name="Test User",
        email=email.lower(),
        password_hash="not-a-real-hash",
        role=role,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def test_user_email_unique_constraint(db_session: Session):
    _make_user(db_session, email="owner@example.com")
    with pytest.raises(IntegrityError):
        _make_user(db_session, email="owner@example.com")


def test_user_role_check_constraint(db_session: Session):
    user = User(
        name="Bad Role",
        email="bad-role@example.com",
        password_hash="not-a-real-hash",
        role="SUPERUSER",
        is_active=True,
    )
    db_session.add(user)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_document_owner_relationship(db_session: Session):
    owner = _make_user(db_session, email="doc-owner@example.com")
    document = Document(
        owner_id=owner.id,
        title="Contract",
        category="HR",
        description="Optional",
        storage_key=f"objects/{uuid.uuid4()}",
        mime_type="application/pdf",
        file_size=1024,
        sha256_checksum="a" * 64,
    )
    db_session.add(document)
    db_session.flush()

    loaded = db_session.scalar(select(Document).where(Document.id == document.id))
    assert loaded is not None
    assert loaded.owner.id == owner.id
    assert loaded.owner.email == "doc-owner@example.com"


def test_active_permission_partial_unique_index(db_session: Session):
    owner = _make_user(db_session, email="grant-owner@example.com", role="OWNER")
    viewer = _make_user(db_session, email="grant-viewer@example.com", role="VIEWER")
    document = Document(
        owner_id=owner.id,
        title="Shared",
        category="Finance",
        storage_key=f"objects/{uuid.uuid4()}",
        mime_type="application/pdf",
        file_size=2048,
        sha256_checksum="b" * 64,
    )
    db_session.add(document)
    db_session.flush()

    active = DocumentPermission(
        document_id=document.id,
        user_id=viewer.id,
        permission="READ",
        granted_by=owner.id,
    )
    db_session.add(active)
    db_session.flush()

    duplicate_active = DocumentPermission(
        document_id=document.id,
        user_id=viewer.id,
        permission="EDIT",
        granted_by=owner.id,
    )
    db_session.add(duplicate_active)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_revoked_permission_allows_new_active_grant(db_session: Session):
    owner = _make_user(db_session, email="revoke-owner@example.com", role="OWNER")
    viewer = _make_user(db_session, email="revoke-viewer@example.com", role="VIEWER")
    document = Document(
        owner_id=owner.id,
        title="Shared Again",
        category="Finance",
        storage_key=f"objects/{uuid.uuid4()}",
        mime_type="application/pdf",
        file_size=2048,
        sha256_checksum="c" * 64,
    )
    db_session.add(document)
    db_session.flush()

    revoked = DocumentPermission(
        document_id=document.id,
        user_id=viewer.id,
        permission="READ",
        granted_by=owner.id,
        revoked_at=datetime.now(timezone.utc),
    )
    db_session.add(revoked)
    db_session.flush()

    regranted = DocumentPermission(
        document_id=document.id,
        user_id=viewer.id,
        permission="EDIT",
        granted_by=owner.id,
    )
    db_session.add(regranted)
    db_session.flush()

    assert revoked.is_active is False
    assert regranted.is_active is True


def test_audit_event_nullable_actor_and_metadata(db_session: Session):
    event = AuditEvent(
        actor_id=None,
        action="LOGIN_FAILED",
        outcome="DENIED",
        reason_code="INVALID_CREDENTIALS",
        request_id="req-test-1",
        metadata_json={"email_domain": "example.com"},
        previous_hash=None,
        event_hash="d" * 64,
    )
    db_session.add(event)
    db_session.flush()

    loaded = db_session.scalar(select(AuditEvent).where(AuditEvent.id == event.id))
    assert loaded is not None
    assert loaded.actor_id is None
    assert loaded.metadata_json["email_domain"] == "example.com"
    assert loaded.created_at.tzinfo is not None
