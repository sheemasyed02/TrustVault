"""Centralized document authorization policy tests.

Endpoint-level download regression coverage lives in
`tests/test_document_access.py`. This suite covers the authorization service
those routes call.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import Document, DocumentPermission, User
from app.services.document_authorization import (
    DocumentAction,
    DocumentAuthorizationError,
    evaluate_document_access,
    reject_protected_metadata_fields,
    require_document_delete,
    require_document_edit,
    require_document_owner,
    require_document_read,
)


def _user(
    session: Session,
    *,
    role: str = "VIEWER",
    is_active: bool = True,
) -> User:
    user = User(
        name=f"{role} User",
        email=f"{role.lower()}-{uuid.uuid4()}@example.com",
        password_hash=hash_password("test-password-12"),
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user


def _document(session: Session, owner: User, *, deleted: bool = False) -> Document:
    doc = Document(
        owner_id=owner.id,
        title="Confidential Contract",
        category="HR",
        description="secret-description",
        storage_key=f"objects/{uuid.uuid4()}",
        mime_type="application/pdf",
        file_size=2048,
        sha256_checksum="a" * 64,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    session.add(doc)
    session.flush()
    return doc


def _grant(
    session: Session,
    *,
    document: Document,
    user: User,
    permission: str,
    granted_by: User,
    revoked: bool = False,
) -> DocumentPermission:
    grant = DocumentPermission(
        document_id=document.id,
        user_id=user.id,
        permission=permission,
        granted_by=granted_by.id,
        revoked_at=datetime.now(timezone.utc) if revoked else None,
    )
    session.add(grant)
    session.flush()
    return grant


def test_owner_can_read(db_session: Session):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    result = require_document_read(db_session, user=owner, document_id=doc.id)
    assert result.id == doc.id


def test_owner_can_edit_metadata(db_session: Session):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    result = require_document_edit(db_session, user=owner, document_id=doc.id)
    assert result.id == doc.id


def test_owner_can_manage_permissions(db_session: Session):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    result = require_document_owner(db_session, user=owner, document_id=doc.id)
    assert result.id == doc.id


def test_owner_can_pass_delete_policy(db_session: Session):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    result = require_document_delete(db_session, user=owner, document_id=doc.id)
    assert result.id == doc.id


def test_read_grantee_can_read(db_session: Session):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    _grant(
        db_session,
        document=doc,
        user=reader,
        permission="READ",
        granted_by=owner,
    )
    assert require_document_read(db_session, user=reader, document_id=doc.id).id == doc.id


def test_read_grantee_cannot_edit_metadata(db_session: Session):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    _grant(
        db_session,
        document=doc,
        user=reader,
        permission="READ",
        granted_by=owner,
    )
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_edit(db_session, user=reader, document_id=doc.id)
    assert exc.value.status_code == 403
    assert "Confidential" not in exc.value.detail


def test_read_grantee_cannot_share_or_revoke(db_session: Session):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    _grant(
        db_session,
        document=doc,
        user=reader,
        permission="READ",
        granted_by=owner,
    )
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_owner(db_session, user=reader, document_id=doc.id)
    assert exc.value.status_code == 403


def test_edit_grantee_can_read(db_session: Session):
    owner = _user(db_session, role="OWNER")
    editor = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    _grant(
        db_session,
        document=doc,
        user=editor,
        permission="EDIT",
        granted_by=owner,
    )
    assert require_document_read(db_session, user=editor, document_id=doc.id).id == doc.id


def test_edit_grantee_can_edit_metadata(db_session: Session):
    owner = _user(db_session, role="OWNER")
    editor = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    _grant(
        db_session,
        document=doc,
        user=editor,
        permission="EDIT",
        granted_by=owner,
    )
    assert require_document_edit(db_session, user=editor, document_id=doc.id).id == doc.id


def test_edit_grantee_cannot_share_or_revoke(db_session: Session):
    owner = _user(db_session, role="OWNER")
    editor = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    _grant(
        db_session,
        document=doc,
        user=editor,
        permission="EDIT",
        granted_by=owner,
    )
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_owner(db_session, user=editor, document_id=doc.id)
    assert exc.value.status_code == 403


def test_edit_grantee_cannot_delete(db_session: Session):
    owner = _user(db_session, role="OWNER")
    editor = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    _grant(
        db_session,
        document=doc,
        user=editor,
        permission="EDIT",
        granted_by=owner,
    )
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_delete(db_session, user=editor, document_id=doc.id)
    assert exc.value.status_code == 403


def test_no_grant_cannot_read(db_session: Session):
    owner = _user(db_session, role="OWNER")
    stranger = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_read(db_session, user=stranger, document_id=doc.id)
    assert exc.value.status_code == 404
    assert "Confidential" not in exc.value.detail
    assert "secret-description" not in exc.value.detail


def test_no_grant_cannot_download_via_read_policy(db_session: Session):
    """Download will use the same READ policy as metadata access."""
    owner = _user(db_session, role="OWNER")
    stranger = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_read(db_session, user=stranger, document_id=doc.id)
    assert exc.value.status_code == 404


def test_no_grant_cannot_edit(db_session: Session):
    owner = _user(db_session, role="OWNER")
    stranger = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_edit(db_session, user=stranger, document_id=doc.id)
    assert exc.value.status_code == 404


def test_no_grant_cannot_share_revoke_or_delete(db_session: Session):
    owner = _user(db_session, role="OWNER")
    stranger = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    for fn in (require_document_owner, require_document_delete):
        with pytest.raises(DocumentAuthorizationError) as exc:
            fn(db_session, user=stranger, document_id=doc.id)
        assert exc.value.status_code == 404


def test_revoked_read_grant_denied(db_session: Session):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    _grant(
        db_session,
        document=doc,
        user=reader,
        permission="READ",
        granted_by=owner,
        revoked=True,
    )
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_read(db_session, user=reader, document_id=doc.id)
    assert exc.value.status_code == 404
    assert exc.value.reason_code == "NO_ACTIVE_GRANT"


def test_revoked_edit_grant_denied(db_session: Session):
    owner = _user(db_session, role="OWNER")
    editor = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    _grant(
        db_session,
        document=doc,
        user=editor,
        permission="EDIT",
        granted_by=owner,
        revoked=True,
    )
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_edit(db_session, user=editor, document_id=doc.id)
    assert exc.value.status_code == 404


def test_missing_grant_denied(db_session: Session):
    owner = _user(db_session, role="OWNER")
    other = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_read(db_session, user=other, document_id=doc.id)
    assert exc.value.reason_code == "NO_ACTIVE_GRANT"


def test_admin_without_grant_cannot_read_content(db_session: Session):
    owner = _user(db_session, role="OWNER")
    admin = _user(db_session, role="ADMIN")
    doc = _document(db_session, owner)
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_read(db_session, user=admin, document_id=doc.id)
    assert exc.value.status_code == 404


def test_admin_without_grant_cannot_download_content(db_session: Session):
    owner = _user(db_session, role="OWNER")
    admin = _user(db_session, role="ADMIN")
    doc = _document(db_session, owner)
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_read(db_session, user=admin, document_id=doc.id)
    assert exc.value.status_code == 404


def test_inactive_account_denied(db_session: Session):
    owner = _user(db_session, role="OWNER")
    inactive = _user(db_session, role="VIEWER", is_active=False)
    doc = _document(db_session, owner)
    _grant(
        db_session,
        document=doc,
        user=inactive,
        permission="EDIT",
        granted_by=owner,
    )
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_read(db_session, user=inactive, document_id=doc.id)
    assert exc.value.status_code == 401


def test_nonexistent_document_denied(db_session: Session):
    user = _user(db_session, role="OWNER")
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_read(db_session, user=user, document_id=uuid.uuid4())
    assert exc.value.status_code == 404
    assert exc.value.reason_code == "DOCUMENT_MISSING_OR_DELETED"


def test_soft_deleted_document_denied(db_session: Session):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner, deleted=True)
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_read(db_session, user=owner, document_id=doc.id)
    assert exc.value.status_code == 404


def test_guessed_document_id_does_not_bypass(db_session: Session):
    owner = _user(db_session, role="OWNER")
    attacker = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    guessed = uuid.uuid4()
    assert guessed != doc.id
    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_read(db_session, user=attacker, document_id=guessed)
    assert exc.value.status_code == 404


def test_client_supplied_owner_or_role_fields_do_not_grant_access(db_session: Session):
    owner = _user(db_session, role="OWNER")
    attacker = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)

    # Spoofed request data must not influence the DB-backed decision.
    spoofed_payload = {
        "owner_id": str(attacker.id),
        "role": "ADMIN",
        "permission": "EDIT",
        "title": "hacked",
    }
    with pytest.raises(DocumentAuthorizationError):
        reject_protected_metadata_fields(spoofed_payload)

    with pytest.raises(DocumentAuthorizationError) as exc:
        evaluate_document_access(
            db_session,
            user=attacker,
            document_id=doc.id,
            action=DocumentAction.READ,
        )
    assert exc.value.status_code == 404


def test_database_failure_fails_closed(db_session: Session):
    owner = _user(db_session, role="OWNER")
    doc = _document(db_session, owner)
    broken = MagicMock()
    broken.get.side_effect = SQLAlchemyError("simulated failure")

    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_read(broken, user=owner, document_id=doc.id)
    assert exc.value.status_code == 503
    assert exc.value.reason_code == "AUTHORIZATION_QUERY_FAILED"


def test_revocation_takes_effect_on_next_check(db_session: Session):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    doc = _document(db_session, owner)
    grant = _grant(
        db_session,
        document=doc,
        user=reader,
        permission="READ",
        granted_by=owner,
    )
    assert require_document_read(db_session, user=reader, document_id=doc.id).id == doc.id

    grant.revoked_at = datetime.now(timezone.utc)
    db_session.flush()

    with pytest.raises(DocumentAuthorizationError) as exc:
        require_document_read(db_session, user=reader, document_id=doc.id)
    assert exc.value.status_code == 404
