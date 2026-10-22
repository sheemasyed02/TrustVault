"""Durable audit hash-chain, admin APIs, and tamper detection."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.documents import get_document_audit, get_storage, get_upload_audit
from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import AuditEvent, User
from app.db.session import get_db, get_session_factory, reset_engine
from app.main import app
from app.services.audit_trail import (
    append_audit_event,
    append_audit_event_committed,
    compute_event_hash,
    sanitize_metadata,
    verify_audit_chain,
)
from app.services.upload_audit import RecordingUploadAuditHook

TEST_JWT_SECRET = "unit-test-jwt-secret-key-32chars-min"


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
def client(
    db_session: Session,
    auth_settings: Settings,
) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield db_session

    # Keep document routes on the in-memory recorder so unrelated suites stay
    # isolated; audit_trail tests exercise DurableAuditHook / admin APIs directly.
    recorder = RecordingUploadAuditHook()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_upload_audit] = lambda: recorder
    app.dependency_overrides[get_document_audit] = lambda: recorder
    app.dependency_overrides[get_storage] = lambda: MagicMock()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _user(
    session: Session,
    *,
    role: str,
    email: str | None = None,
    is_active: bool = True,
) -> User:
    user = User(
        name=f"{role} Audit",
        email=email or f"{role.lower()}-{uuid.uuid4()}@example.com",
        password_hash=hash_password("audit-password-12"),
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user


def _auth(user: User, settings: Settings) -> dict[str, str]:
    token, _ = create_access_token(subject_user_id=user.id, settings=settings)
    return {"Authorization": f"Bearer {token}"}


def _committed_reset_audit_chain() -> None:
    """Delete all audit rows in a committed transaction (shared test DB cleanup)."""
    session = get_session_factory()()
    try:
        session.execute(text("DELETE FROM audit_events"))
        session.commit()
    finally:
        session.close()


def test_compute_event_hash_is_deterministic():
    eid = uuid.UUID("11111111-1111-1111-1111-111111111111")
    ts = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)
    a = compute_event_hash(
        event_id=eid,
        created_at=ts,
        actor_id=None,
        action="LOGIN",
        document_id=None,
        target_user_id=None,
        outcome="SUCCESS",
        reason_code=None,
        request_id="req-1",
        metadata={},
        previous_hash=None,
    )
    b = compute_event_hash(
        event_id=eid,
        created_at=ts,
        actor_id=None,
        action="LOGIN",
        document_id=None,
        target_user_id=None,
        outcome="SUCCESS",
        reason_code=None,
        request_id="req-1",
        metadata={},
        previous_hash=None,
    )
    assert a == b
    assert len(a) == 64


def test_sanitize_metadata_strips_secrets():
    clean = sanitize_metadata(
        {
            "changed_fields": ["title"],
            "password": "nope",
            "access_token": "jwt-here",
            "nested": {"token": "x", "ok": 1},
            "file_bytes": b"abc",
        }
    )
    assert clean == {"changed_fields": ["title"], "nested": {"ok": 1}}
    assert "password" not in clean
    assert "access_token" not in clean
    assert "file_bytes" not in clean


def test_empty_chain_verification(db_session: Session):
    _committed_reset_audit_chain()
    result = verify_audit_chain(db_session)
    assert result.valid is True
    assert result.event_count == 0
    assert result.reason_code == "EMPTY_CHAIN"


def test_sequential_append_links_previous_hash(db_session: Session):
    _committed_reset_audit_chain()

    first = append_audit_event(
        db_session,
        action="LOGIN",
        outcome="SUCCESS",
        actor_id=None,
        request_id="a",
    )
    second = append_audit_event(
        db_session,
        action="DOCUMENT_UPLOAD",
        outcome="SUCCESS",
        actor_id=None,
        request_id="b",
    )
    assert first.previous_hash is None
    assert second.previous_hash == first.event_hash
    assert verify_audit_chain(db_session).valid is True


def test_tamper_field_and_hash_and_link_detected(db_session: Session):
    _committed_reset_audit_chain()
    e1 = append_audit_event(db_session, action="LOGIN", outcome="SUCCESS")
    e2 = append_audit_event(db_session, action="LOGIN", outcome="DENIED", reason_code="X")
    db_session.flush()

    # Modified field without updating hash
    e1.action = "TAMPERED"
    db_session.flush()
    bad = verify_audit_chain(db_session)
    assert bad.valid is False
    assert bad.reason_code == "EVENT_HASH_MISMATCH"

    # Restore action, break stored hash
    e1.action = "LOGIN"
    e1.event_hash = "0" * 64
    db_session.flush()
    bad_hash = verify_audit_chain(db_session)
    assert bad_hash.valid is False
    assert bad_hash.reason_code == "EVENT_HASH_MISMATCH"

    # Fix e1 hash, break previous link on e2
    e1.event_hash = compute_event_hash(
        event_id=e1.id,
        created_at=e1.created_at,
        actor_id=e1.actor_id,
        action=e1.action,
        document_id=e1.document_id,
        target_user_id=e1.target_user_id,
        outcome=e1.outcome,
        reason_code=e1.reason_code,
        request_id=e1.request_id,
        metadata=dict(e1.metadata_json or {}),
        previous_hash=e1.previous_hash,
    )
    e2.previous_hash = "f" * 64
    db_session.flush()
    bad_link = verify_audit_chain(db_session)
    assert bad_link.valid is False
    assert bad_link.reason_code == "PREVIOUS_HASH_MISMATCH"


def test_reordering_breaks_previous_hash_links(db_session: Session):
    _committed_reset_audit_chain()
    e1 = append_audit_event(db_session, action="A", outcome="SUCCESS")
    e2 = append_audit_event(db_session, action="B", outcome="SUCCESS")
    # Swap created_at so verification order changes relative to hash links.
    ts1, ts2 = e1.created_at, e2.created_at
    e1.created_at = ts2
    e2.created_at = ts1
    db_session.flush()
    result = verify_audit_chain(db_session)
    assert result.valid is False
    assert result.reason_code in {"PREVIOUS_HASH_MISMATCH", "EVENT_HASH_MISMATCH"}


def test_denied_event_survives_request_rollback(db_session: Session):
    """Independent denial commit is not erased by rolling back another session."""
    marker = f"deny-survive-{uuid.uuid4()}"
    event = append_audit_event_committed(
        action="DOCUMENT_READ",
        outcome="DENIED",
        reason_code="NOT_AUTHORIZED",
        request_id=marker,
        document_id=uuid.uuid4(),
    )
    assert event.id is not None

    # Simulate failed protected operation transaction.
    db_session.rollback()
    db_session.begin()

    loaded = db_session.scalar(
        select(AuditEvent).where(AuditEvent.request_id == marker)
    )
    assert loaded is not None
    assert loaded.outcome == "DENIED"

    # Cleanup the independently committed row without ending the fixture txn.
    cleaner = get_session_factory()()
    try:
        cleaner.execute(
            text("DELETE FROM audit_events WHERE request_id = :r"),
            {"r": marker},
        )
        cleaner.commit()
    finally:
        cleaner.close()


def test_concurrent_appends_keep_valid_chain():
    """Serialized advisory lock should keep the chain valid under concurrency."""
    _committed_reset_audit_chain()
    factory = get_session_factory()
    prefix = f"concurrent-{uuid.uuid4()}"
    barrier = threading.Barrier(8)

    def write_one(i: int) -> str:
        session = factory()
        try:
            barrier.wait(timeout=10)
            event = append_audit_event(
                session,
                action="CONCURRENT_APPEND",
                outcome="SUCCESS",
                request_id=f"{prefix}-{i}",
            )
            session.commit()
            return event.event_hash
        finally:
            session.close()

    hashes: list[str] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(write_one, i) for i in range(8)]
        for fut in as_completed(futures):
            hashes.append(fut.result())

    assert len(hashes) == 8
    assert len(set(hashes)) == 8

    session = factory()
    try:
        result = verify_audit_chain(session)
        assert result.valid is True
        assert result.event_count == 8
    finally:
        session.close()
    _committed_reset_audit_chain()


def test_non_admin_denied_audit_endpoints(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = _user(db_session, role="OWNER")
    headers = _auth(owner, auth_settings)
    assert client.get("/admin/audit/events", headers=headers).status_code == 403
    assert client.get("/admin/audit/integrity", headers=headers).status_code == 403
    assert client.get("/admin/users", headers=headers).status_code == 403


def test_admin_list_and_filter_and_integrity(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    _committed_reset_audit_chain()
    admin = _user(db_session, role="ADMIN")
    actor = _user(db_session, role="OWNER")
    append_audit_event(
        db_session,
        action="DOCUMENT_DOWNLOAD",
        outcome="SUCCESS",
        actor_id=actor.id,
        request_id="filter-me",
    )
    append_audit_event(
        db_session,
        action="DOCUMENT_DOWNLOAD",
        outcome="DENIED",
        actor_id=actor.id,
        reason_code="NOT_AUTHORIZED",
    )

    headers = _auth(admin, auth_settings)
    listed = client.get(
        "/admin/audit/events",
        headers=headers,
        params={"actor_id": str(actor.id), "outcome": "SUCCESS", "action": "DOCUMENT_DOWNLOAD"},
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] >= 1
    assert all(row["outcome"] == "SUCCESS" for row in body["results"])
    assert all(row["action"] == "DOCUMENT_DOWNLOAD" for row in body["results"])
    for row in body["results"]:
        assert "password" not in row.get("metadata", {})
        assert "access_token" not in row.get("metadata", {})

    # Integrity over the request txn view (includes uncommitted appends).
    assert verify_audit_chain(db_session).valid is True
    integrity = client.get("/admin/audit/integrity", headers=headers)
    assert integrity.status_code == 200
    # Admin integrity uses the same request session override in tests.
    assert integrity.json()["valid"] is True


def test_admin_user_status_change_is_audited(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    admin = _user(db_session, role="ADMIN")
    target = _user(db_session, role="VIEWER")
    headers = _auth(admin, auth_settings)

    resp = client.patch(
        f"/admin/users/{target.id}",
        headers=headers,
        json={"is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    events = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "ADMIN_USER_STATUS_UPDATE",
                AuditEvent.target_user_id == target.id,
            )
        ).all()
    )
    assert events
    assert events[-1].outcome == "SUCCESS"
    assert events[-1].reason_code == "DEACTIVATED"
    assert "password" not in (events[-1].metadata_json or {})


def test_no_ordinary_audit_mutation_endpoints(client: TestClient, auth_settings: Settings, db_session: Session):
    admin = _user(db_session, role="ADMIN")
    headers = _auth(admin, auth_settings)
    fake_id = uuid.uuid4()
    assert client.patch(f"/admin/audit/events/{fake_id}", headers=headers).status_code in {404, 405}
    assert client.delete(f"/admin/audit/events/{fake_id}", headers=headers).status_code in {404, 405}
    assert client.put(f"/admin/audit/events/{fake_id}", headers=headers).status_code in {404, 405}


def test_login_success_creates_audit_event(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = _user(db_session, role="OWNER", email=f"login-ok-{uuid.uuid4()}@example.com")
    ok = client.post(
        "/auth/login",
        json={"email": user.email, "password": "audit-password-12"},
    )
    assert ok.status_code == 200
    success_events = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "LOGIN",
                AuditEvent.outcome == "SUCCESS",
                AuditEvent.actor_id == user.id,
            )
        ).all()
    )
    assert success_events


def test_login_failure_creates_denied_audit_event(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    """DENIED login commits independently (separate from SUCCESS-audit lock hold)."""
    # Persist the user in a committed session so login can authenticate lookup
    # and the independent denial writer can attribute actor_id.
    email = f"login-bad-{uuid.uuid4()}@example.com"
    user_id = None
    writer = get_session_factory()()
    try:
        user = User(
            name="Owner Audit",
            email=email,
            password_hash=hash_password("audit-password-12"),
            role="OWNER",
            is_active=True,
        )
        writer.add(user)
        writer.commit()
        user_id = user.id
    finally:
        writer.close()

    try:
        bad = client.post(
            "/auth/login",
            json={"email": email, "password": "wrong-password-xx"},
        )
        assert bad.status_code == 401
        denied = db_session.scalar(
            select(AuditEvent)
            .where(
                AuditEvent.action == "LOGIN",
                AuditEvent.outcome == "DENIED",
                AuditEvent.actor_id == user_id,
                AuditEvent.reason_code == "INVALID_CREDENTIALS",
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(1)
        )
        assert denied is not None
        meta = denied.metadata_json or {}
        assert "password" not in meta
        assert "token" not in meta
    finally:
        # Independently committed user + DENIED audit must not pollute the live DB.
        cleaner = get_session_factory()()
        try:
            if user_id is not None:
                cleaner.execute(
                    text("DELETE FROM audit_events WHERE actor_id = :uid"),
                    {"uid": str(user_id)},
                )
                cleaner.execute(
                    text("DELETE FROM users WHERE id = :uid"),
                    {"uid": str(user_id)},
                )
                cleaner.commit()
        finally:
            cleaner.close()
