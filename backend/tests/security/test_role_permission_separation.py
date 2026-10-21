"""Regression: platform roles vs document grants stay separate.

Part 5 checklist for TrustVault authorization rules. Isolated fixtures only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from tests.security.conftest import (
    DOCX_BYTES,
    auth_header,
    grant_permission,
    make_document,
    make_user,
)


def test_admin_audit_ok_but_cannot_download_unshared(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    owner = make_user(db_session, role="OWNER")
    admin = make_user(db_session, role="ADMIN")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    headers = auth_header(admin, auth_settings)

    assert client.get("/admin/audit/events", headers=headers).status_code == 200
    assert client.get("/admin/audit/integrity", headers=headers).status_code == 200
    assert client.get(f"/documents/{doc.id}/download", headers=headers).status_code == 404
    storage_mock.open_object.assert_not_called()


def test_admin_with_explicit_read_grant_can_download(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    """ADMIN may access content only via ownership or an active grant."""
    owner = make_user(db_session, role="OWNER")
    admin = make_user(db_session, role="ADMIN")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    grant_permission(
        db_session, document=doc, user=admin, permission="READ", granted_by=owner
    )
    headers = auth_header(admin, auth_settings)

    meta = client.get(f"/documents/{doc.id}", headers=headers)
    assert meta.status_code == 200
    assert meta.json()["your_access"] == "READ"
    assert client.get("/users/me", headers=headers).json()["role"] == "ADMIN"

    download = client.get(f"/documents/{doc.id}/download", headers=headers)
    assert download.status_code == 200
    assert download.content == DOCX_BYTES


def test_owner_can_manage_own_document(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    owner = make_user(db_session, role="OWNER")
    viewer = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    headers = auth_header(owner, auth_settings)

    assert client.get(f"/documents/{doc.id}", headers=headers).json()["your_access"] == "OWNER"
    assert client.get(f"/documents/{doc.id}/download", headers=headers).status_code == 200
    assert (
        client.patch(
            f"/documents/{doc.id}",
            headers=headers,
            json={"title": "Owned Title"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/documents/{doc.id}/permissions",
            headers=headers,
            json={"user_id": str(viewer.id), "permission": "READ"},
        ).status_code
        == 201
    )
    assert (
        client.delete(
            f"/documents/{doc.id}/permissions/{viewer.id}",
            headers=headers,
        ).status_code
        == 200
    )


def test_viewer_read_can_download_not_edit_metadata(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    owner = make_user(db_session, role="OWNER")
    reader = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    grant_permission(
        db_session, document=doc, user=reader, permission="READ", granted_by=owner
    )
    headers = auth_header(reader, auth_settings)

    assert client.get(f"/documents/{doc.id}/download", headers=headers).status_code == 200
    assert (
        client.patch(
            f"/documents/{doc.id}",
            headers=headers,
            json={"title": "Nope"},
        ).status_code
        == 403
    )
    me = client.get("/users/me", headers=headers).json()
    assert me["role"] == "VIEWER"


def test_viewer_edit_can_patch_metadata_not_share_or_delete(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    owner = make_user(db_session, role="OWNER")
    editor = make_user(db_session, role="VIEWER")
    other = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    grant_permission(
        db_session, document=doc, user=editor, permission="EDIT", granted_by=owner
    )
    headers = auth_header(editor, auth_settings)

    patched = client.patch(
        f"/documents/{doc.id}",
        headers=headers,
        json={"title": "Editor Ok", "category": "Legal"},
    )
    assert patched.status_code == 200
    assert patched.json()["your_access"] == "EDIT"

    assert (
        client.post(
            f"/documents/{doc.id}/permissions",
            headers=headers,
            json={"user_id": str(other.id), "permission": "READ"},
        ).status_code
        == 403
    )
    assert client.delete(f"/documents/{doc.id}", headers=headers).status_code == 403
    assert client.get("/users/me", headers=headers).json()["role"] == "VIEWER"


def test_user_without_grant_cannot_access(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    owner = make_user(db_session, role="OWNER")
    stranger = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    headers = auth_header(stranger, auth_settings)

    assert client.get(f"/documents/{doc.id}", headers=headers).status_code == 404
    assert client.get(f"/documents/{doc.id}/download", headers=headers).status_code == 404
    storage_mock.open_object.assert_not_called()


def test_revoked_access_denied_on_next_request_same_token(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    owner = make_user(db_session, role="OWNER")
    reader = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    grant = grant_permission(
        db_session, document=doc, user=reader, permission="READ", granted_by=owner
    )
    headers = auth_header(reader, auth_settings)

    assert client.get(f"/documents/{doc.id}/download", headers=headers).status_code == 200
    grant.revoked_at = datetime.now(timezone.utc)
    db_session.flush()
    storage_mock.open_object.reset_mock()
    assert client.get(f"/documents/{doc.id}/download", headers=headers).status_code == 404
    storage_mock.open_object.assert_not_called()


def test_disabled_account_cannot_use_protected_endpoints(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = make_user(db_session, role="OWNER", is_active=True)
    headers = auth_header(user, auth_settings)
    assert client.get("/users/me", headers=headers).status_code == 200

    user.is_active = False
    db_session.flush()
    assert client.get("/users/me", headers=headers).status_code == 401
    assert client.get("/documents", headers=headers).status_code == 401


def test_client_role_and_id_fields_do_not_bypass_authorization(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = make_user(db_session, role="OWNER")
    attacker = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner)
    headers = auth_header(attacker, auth_settings)

    # Forged document id → 404; no elevation via query params.
    forged = uuid.uuid4()
    assert client.get(f"/documents/{forged}", headers=headers).status_code == 404

    # Body role / owner_id / granted_by rejected on grant attempt for non-owner.
    assert (
        client.post(
            f"/documents/{doc.id}/permissions",
            headers=headers,
            json={
                "user_id": str(attacker.id),
                "permission": "EDIT",
                "role": "ADMIN",
                "granted_by": str(attacker.id),
                "owner_id": str(attacker.id),
            },
        ).status_code
        in {403, 404, 422}
    )

    # Attacker still VIEWER; cannot read the document.
    assert client.get("/users/me", headers=headers).json()["role"] == "VIEWER"
    assert client.get(f"/documents/{doc.id}", headers=headers).status_code == 404


def test_document_grant_does_not_promote_platform_role(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    """READ/EDIT grants must not change users.role to OWNER or ADMIN."""
    owner = make_user(db_session, role="OWNER")
    viewer = make_user(db_session, role="VIEWER")
    admin_target = make_user(db_session, role="ADMIN")
    doc = make_document(db_session, owner)
    owner_headers = auth_header(owner, auth_settings)

    grant_read = client.post(
        f"/documents/{doc.id}/permissions",
        headers=owner_headers,
        json={"user_id": str(viewer.id), "permission": "READ"},
    )
    assert grant_read.status_code == 201

    grant_edit = client.post(
        f"/documents/{doc.id}/permissions",
        headers=owner_headers,
        json={"user_id": str(admin_target.id), "permission": "EDIT"},
    )
    assert grant_edit.status_code == 201

    # Platform roles unchanged in PostgreSQL and /users/me.
    db_session.refresh(viewer)
    db_session.refresh(admin_target)
    assert viewer.role == "VIEWER"
    assert admin_target.role == "ADMIN"

    viewer_me = client.get("/users/me", headers=auth_header(viewer, auth_settings))
    assert viewer_me.status_code == 200
    assert viewer_me.json()["role"] == "VIEWER"

    admin_me = client.get(
        "/users/me", headers=auth_header(admin_target, auth_settings)
    )
    assert admin_me.json()["role"] == "ADMIN"

    # your_access reflects document grant, not platform role promotion.
    viewer_detail = client.get(
        f"/documents/{doc.id}",
        headers=auth_header(viewer, auth_settings),
    )
    assert viewer_detail.json()["your_access"] == "READ"

    admin_detail = client.get(
        f"/documents/{doc.id}",
        headers=auth_header(admin_target, auth_settings),
    )
    assert admin_detail.json()["your_access"] == "EDIT"

    # Cannot grant platform-like permission values.
    bad = client.post(
        f"/documents/{doc.id}/permissions",
        headers=owner_headers,
        json={"user_id": str(uuid.uuid4()), "permission": "OWNER"},
    )
    # Target missing or invalid permission — either way not a role promotion.
    assert bad.status_code in {404, 422}


def test_owner_cannot_modify_others_document_without_grant(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    owner_a = make_user(db_session, role="OWNER")
    owner_b = make_user(db_session, role="OWNER")
    doc = make_document(db_session, owner_a)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    headers = auth_header(owner_b, auth_settings)

    assert client.get(f"/documents/{doc.id}", headers=headers).status_code == 404
    assert (
        client.patch(
            f"/documents/{doc.id}",
            headers=headers,
            json={"title": "Stolen"},
        ).status_code
        == 404
    )
    assert client.delete(f"/documents/{doc.id}", headers=headers).status_code == 404
