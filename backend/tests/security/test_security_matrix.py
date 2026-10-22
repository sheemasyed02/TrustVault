"""Security test matrix for TrustVault document access control.

Each test documents:
- Actor role / account state
- Document ownership and grants
- Request attempted
- Expected status / behavior
- Whether an audit DENIED/SUCCESS event is expected (via RecordingUploadAuditHook)

Isolated fixtures only — no demo seed dependency.
Inaccessible resources use the project policy of **404** (enumeration-resistant)
unless the principal has a relationship but lacks the action (**403**).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.upload_audit import RecordingUploadAuditHook
from tests.security.conftest import (
    DOCX_BYTES,
    auth_header,
    grant_permission,
    make_document,
    make_user,
)


# ---------------------------------------------------------------------------
# A. Owner
# ---------------------------------------------------------------------------


def test_matrix_owner_can_list_read_download_edit_share_delete(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
    storage_mock,
):
    """Owner / own doc / GET list+meta+download, PATCH, grant, DELETE → 200.

    Audit: SUCCESS on download/delete paths when hooks fire.
    """
    owner = make_user(db_session, role="OWNER")
    viewer = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    headers = auth_header(owner, auth_settings)

    listed = client.get("/documents", headers=headers)
    assert listed.status_code == 200
    assert any(row["id"] == str(doc.id) for row in listed.json()["results"])

    meta = client.get(f"/documents/{doc.id}", headers=headers)
    assert meta.status_code == 200
    assert meta.json()["your_access"] == "OWNER"
    assert "storage_key" not in meta.json()

    download = client.get(f"/documents/{doc.id}/download", headers=headers)
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")
    inline = client.get(
        f"/documents/{doc.id}/download",
        params={"disposition": "inline"},
        headers=headers,
    )
    assert inline.status_code == 200
    assert inline.content == DOCX_BYTES

    patched = client.patch(
        f"/documents/{doc.id}",
        headers=headers,
        json={"title": "Owner Updated"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Owner Updated"

    grant = client.post(
        f"/documents/{doc.id}/permissions",
        headers=headers,
        json={"user_id": str(viewer.id), "permission": "READ"},
    )
    assert grant.status_code in {200, 201}

    deleted = client.delete(f"/documents/{doc.id}", headers=headers)
    assert deleted.status_code == 200
    assert client.get(f"/documents/{doc.id}", headers=headers).status_code == 404


# ---------------------------------------------------------------------------
# B. READ recipient
# ---------------------------------------------------------------------------


def test_matrix_read_grantee_can_read_download_but_not_mutate(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    audit_hook: RecordingUploadAuditHook,
    storage_mock,
):
    """VIEWER + READ grant / shared doc / read+download 200; edit/share/delete denied.

    Denied mutations → 403 (relationship exists) or 404 per route policy.
    Audit: DENIED for forbidden mutations.
    """
    owner = make_user(db_session, role="OWNER")
    reader = make_user(db_session, role="VIEWER")
    other = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    grant_permission(
        db_session, document=doc, user=reader, permission="READ", granted_by=owner
    )
    headers = auth_header(reader, auth_settings)

    assert client.get(f"/documents/{doc.id}", headers=headers).status_code == 200
    assert client.get(f"/documents/{doc.id}", headers=headers).json()["your_access"] == "READ"
    assert client.get(f"/documents/{doc.id}/download", headers=headers).status_code == 200

    assert (
        client.patch(
            f"/documents/{doc.id}",
            headers=headers,
            json={"title": "Hacked"},
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/documents/{doc.id}/content",
            headers=headers,
            json={"text": "Hacked"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/documents/{doc.id}/permissions",
            headers=headers,
            json={"user_id": str(other.id), "permission": "READ"},
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/documents/{doc.id}/permissions/{other.id}",
            headers=headers,
        ).status_code
        in {403, 404}
    )
    assert client.delete(f"/documents/{doc.id}", headers=headers).status_code == 403

    denied_actions = {e["action"] for e in audit_hook.events if e["outcome"] == "DENIED"}
    assert denied_actions  # at least one denial recorded by the hook


# ---------------------------------------------------------------------------
# C. EDIT recipient
# ---------------------------------------------------------------------------


def test_matrix_edit_grantee_can_edit_content_not_metadata_share_or_delete(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    """VIEWER + EDIT grant: content OK; metadata/share/delete forbidden."""
    owner = make_user(db_session, role="OWNER")
    editor = make_user(db_session, role="VIEWER")
    other = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    grant_permission(
        db_session, document=doc, user=editor, permission="EDIT", granted_by=owner
    )
    headers = auth_header(editor, auth_settings)

    meta = client.get(f"/documents/{doc.id}", headers=headers)
    assert meta.status_code == 200
    assert meta.json()["your_access"] == "EDIT"
    assert client.get(f"/documents/{doc.id}/download", headers=headers).status_code == 200

    patched = client.patch(
        f"/documents/{doc.id}",
        headers=headers,
        json={"title": "Editor Title", "category": "Legal"},
    )
    assert patched.status_code == 403

    content = client.put(
        f"/documents/{doc.id}/content",
        headers=headers,
        json={"text": "Edited body from EDIT grantee"},
    )
    assert content.status_code == 200

    # Mass-assignment of owner/storage rejected.
    bad = client.patch(
        f"/documents/{doc.id}",
        headers=headers,
        json={"owner_id": str(editor.id), "storage_key": "evil/key"},
    )
    assert bad.status_code == 422

    assert (
        client.post(
            f"/documents/{doc.id}/permissions",
            headers=headers,
            json={"user_id": str(other.id), "permission": "READ"},
        ).status_code
        == 403
    )
    assert client.delete(f"/documents/{doc.id}", headers=headers).status_code == 403


# ---------------------------------------------------------------------------
# D. Unrelated user / IDOR
# ---------------------------------------------------------------------------


def test_matrix_unrelated_user_cannot_access_or_discover(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
    audit_hook: RecordingUploadAuditHook,
):
    """Unrelated VIEWER / no grant / list empty; meta+download 404; no R2 call.

    Audit: DENIED on download attempt.
    """
    owner = make_user(db_session, role="OWNER")
    stranger = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner, title="Top Secret Matrix")
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    headers = auth_header(stranger, auth_settings)

    listed = client.get("/documents", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 0
    assert listed.json()["results"] == []

    search = client.get(
        "/documents",
        headers=headers,
        params={"title": "Top Secret Matrix"},
    )
    assert search.status_code == 200
    assert search.json()["total"] == 0

    meta = client.get(f"/documents/{doc.id}", headers=headers)
    assert meta.status_code == 404
    assert "Top Secret" not in meta.text

    storage_mock.open_object.reset_mock()
    download = client.get(f"/documents/{doc.id}/download", headers=headers)
    assert download.status_code == 404
    assert DOCX_BYTES not in download.content
    storage_mock.open_object.assert_not_called()

    assert any(
        e["action"] == "DOCUMENT_DOWNLOAD" and e["outcome"] == "DENIED"
        for e in audit_hook.events
    )


def test_matrix_guessed_uuid_and_client_storage_key_ignored(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    """Authenticated OWNER / guessed UUID + query storage_key → 404; R2 unused.

    Server must never open a client-supplied object key.
    """
    owner = make_user(db_session, role="OWNER")
    headers = auth_header(owner, auth_settings)
    forged = uuid.uuid4()

    storage_mock.open_object.reset_mock()
    response = client.get(
        f"/documents/{forged}/download",
        headers=headers,
        params={"storage_key": "objects/someone-elses-key"},
    )
    assert response.status_code == 404
    storage_mock.open_object.assert_not_called()


# ---------------------------------------------------------------------------
# E. Administrator
# ---------------------------------------------------------------------------


def test_matrix_admin_audit_without_document_content(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    """ADMIN / no grant / audit endpoints 200; document meta+download 404."""
    owner = make_user(db_session, role="OWNER")
    admin = make_user(db_session, role="ADMIN")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    headers = auth_header(admin, auth_settings)

    assert client.get("/admin/summary", headers=headers).status_code == 200
    assert client.get("/admin/audit/events", headers=headers).status_code == 200
    assert client.get("/admin/audit/integrity", headers=headers).status_code == 200
    assert client.get(f"/documents/{doc.id}", headers=headers).status_code == 404
    assert client.get(f"/documents/{doc.id}/download", headers=headers).status_code == 404
    storage_mock.open_object.assert_not_called()


# ---------------------------------------------------------------------------
# Immediate revocation + deactivation
# ---------------------------------------------------------------------------


def test_matrix_revoke_read_denies_next_download_same_token(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    """VIEWER + READ then revoked / same JWT / download 200 then 404."""
    owner = make_user(db_session, role="OWNER")
    reader = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    grant = grant_permission(
        db_session, document=doc, user=reader, permission="READ", granted_by=owner
    )
    token_headers = auth_header(reader, auth_settings)

    assert (
        client.get(f"/documents/{doc.id}/download", headers=token_headers).status_code
        == 200
    )

    grant.revoked_at = datetime.now(timezone.utc)
    db_session.flush()
    storage_mock.open_object.reset_mock()

    denied = client.get(f"/documents/{doc.id}/download", headers=token_headers)
    assert denied.status_code == 404
    storage_mock.open_object.assert_not_called()


def test_matrix_revoke_edit_denies_next_content_put_same_token(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    """VIEWER + EDIT then revoked / same JWT / content PUT 200 then 403/404."""
    owner = make_user(db_session, role="OWNER")
    editor = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    grant = grant_permission(
        db_session, document=doc, user=editor, permission="EDIT", granted_by=owner
    )
    headers = auth_header(editor, auth_settings)

    ok = client.put(
        f"/documents/{doc.id}/content",
        headers=headers,
        json={"text": "Still Allowed"},
    )
    assert ok.status_code == 200

    grant.revoked_at = datetime.now(timezone.utc)
    db_session.flush()

    denied = client.put(
        f"/documents/{doc.id}/content",
        headers=headers,
        json={"text": "Should Fail"},
    )
    assert denied.status_code in {403, 404}


def test_matrix_deactivated_user_blocked_with_valid_token(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    """Former active OWNER token / is_active=False / next /users/me → 401."""
    user = make_user(db_session, role="OWNER", is_active=True)
    headers = auth_header(user, auth_settings)
    assert client.get("/users/me", headers=headers).status_code == 200

    user.is_active = False
    db_session.flush()
    assert client.get("/users/me", headers=headers).status_code == 401
    assert client.get("/documents", headers=headers).status_code == 401


# ---------------------------------------------------------------------------
# Tampering / privilege escalation
# ---------------------------------------------------------------------------


def test_matrix_role_and_owner_claims_in_body_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    """OWNER upload/PATCH / client role+owner_id+storage_key → ignored or 422."""
    owner = make_user(db_session, role="OWNER")
    attacker = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner)
    headers = auth_header(owner, auth_settings)

    # Permission grant cannot set granted_by / elevate role via extra fields.
    grant = client.post(
        f"/documents/{doc.id}/permissions",
        headers=headers,
        json={
            "user_id": str(attacker.id),
            "permission": "EDIT",
            "granted_by": str(attacker.id),
            "role": "ADMIN",
        },
    )
    assert grant.status_code == 422

    patch = client.patch(
        f"/documents/{doc.id}",
        headers=headers,
        json={"title": "Ok", "role": "ADMIN", "owner_id": str(attacker.id)},
    )
    assert patch.status_code == 422


def test_matrix_path_traversal_filename_sanitized_on_download(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    """Owner download / original_filename with ../ → Content-Disposition safe."""
    owner = make_user(db_session, role="OWNER")
    doc = make_document(db_session, owner)
    doc.original_filename = "../../etc/passwd.docx"
    db_session.flush()
    storage_mock._store[doc.storage_key] = DOCX_BYTES

    response = client.get(
        f"/documents/{doc.id}/download",
        headers=auth_header(owner, auth_settings),
    )
    assert response.status_code == 200
    disposition = response.headers.get("content-disposition", "")
    assert ".." not in disposition
    assert "/etc/" not in disposition
    assert "passwd" in disposition or "document" in disposition.lower()


# ---------------------------------------------------------------------------
# Non-admin audit gate
# ---------------------------------------------------------------------------


def test_matrix_non_admin_cannot_access_audit_apis(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    """OWNER / admin audit routes → 403."""
    owner = make_user(db_session, role="OWNER")
    headers = auth_header(owner, auth_settings)
    assert client.get("/admin/audit/events", headers=headers).status_code == 403
    assert client.get("/admin/audit/integrity", headers=headers).status_code == 403
    assert client.get("/admin/users", headers=headers).status_code == 403
