"""End-to-end ownership and per-document permission workflow (requirement G).

Uses separate users and real HTTP requests against the FastAPI app.
"""

from __future__ import annotations

import uuid

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


def test_owner_a_cannot_access_owner_b_private_document(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    owner_a = make_user(db_session, role="OWNER")
    owner_b = make_user(db_session, role="OWNER")
    doc_b = make_document(db_session, owner_b, title="B Private")
    storage_mock._store[doc_b.storage_key] = DOCX_BYTES
    headers_a = auth_header(owner_a, auth_settings)

    listed = client.get("/documents", headers=headers_a)
    assert listed.status_code == 200
    assert all(row["id"] != str(doc_b.id) for row in listed.json()["results"])

    assert client.get(f"/documents/{doc_b.id}", headers=headers_a).status_code == 404
    assert (
        client.get(f"/documents/{doc_b.id}/download", headers=headers_a).status_code
        == 404
    )
    storage_mock.open_object.assert_not_called()


def test_viewer_a_can_read_shared_document_viewer_b_cannot(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    owner = make_user(db_session, role="OWNER")
    viewer_a = make_user(db_session, role="VIEWER")
    viewer_b = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner, title="Shared With A Only")
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    grant_permission(
        db_session, document=doc, user=viewer_a, permission="READ", granted_by=owner
    )

    headers_a = auth_header(viewer_a, auth_settings)
    headers_b = auth_header(viewer_b, auth_settings)

    meta_a = client.get(f"/documents/{doc.id}", headers=headers_a)
    assert meta_a.status_code == 200
    assert meta_a.json()["your_access"] == "READ"
    assert meta_a.json()["owner"]["id"] == str(owner.id)
    assert "original_filename" in meta_a.json()
    assert "mime_type" in meta_a.json()
    assert "file_size" in meta_a.json()
    assert "created_at" in meta_a.json()
    assert "updated_at" in meta_a.json()
    assert "storage_key" not in meta_a.json()

    download_a = client.get(
        f"/documents/{doc.id}/download",
        params={"disposition": "inline"},
        headers=headers_a,
    )
    assert download_a.status_code == 200
    assert download_a.content == DOCX_BYTES

    assert client.get(f"/documents/{doc.id}", headers=headers_b).status_code == 404
    assert client.get(f"/documents/{doc.id}/download", headers=headers_b).status_code == 404


def test_read_permission_cannot_modify_content_or_metadata(
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

    assert (
        client.patch(
            f"/documents/{doc.id}",
            headers=headers,
            json={"title": "Hacked", "category": "X", "description": "Y"},
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/documents/{doc.id}/content",
            headers=headers,
            json={"text": "Hacked body"},
        ).status_code
        == 403
    )


def test_edit_permission_cannot_change_metadata_delete_or_share(
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

    # Content edit allowed.
    content = client.put(
        f"/documents/{doc.id}/content",
        headers=headers,
        json={"text": "Legitimate content edit"},
    )
    assert content.status_code == 200
    assert content.json()["your_access"] == "EDIT"

    # Metadata / share / delete forbidden.
    assert (
        client.patch(
            f"/documents/{doc.id}",
            headers=headers,
            json={"title": "Should Fail"},
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


def test_only_owner_can_change_metadata_delete_and_manage_sharing(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    owner = make_user(db_session, role="OWNER")
    editor = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    grant_permission(
        db_session, document=doc, user=editor, permission="EDIT", granted_by=owner
    )
    owner_headers = auth_header(owner, auth_settings)

    patched = client.patch(
        f"/documents/{doc.id}",
        headers=owner_headers,
        json={"title": "Owner Title", "category": "Legal", "description": "Notes"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Owner Title"
    assert patched.json()["your_access"] == "OWNER"

    listed_perms = client.get(
        f"/documents/{doc.id}/permissions",
        headers=owner_headers,
    )
    assert listed_perms.status_code == 200
    assert any(
        row["user"]["id"] == str(editor.id)
        for row in listed_perms.json()["permissions"]
    )

    audit = client.get(f"/documents/{doc.id}/audit", headers=owner_headers)
    assert audit.status_code == 200

    # Editor cannot see owner audit or permission list.
    editor_headers = auth_header(editor, auth_settings)
    assert (
        client.get(f"/documents/{doc.id}/permissions", headers=editor_headers).status_code
        == 403
    )
    assert (
        client.get(f"/documents/{doc.id}/audit", headers=editor_headers).status_code
        in {403, 404}
    )


def test_revocation_blocks_subsequent_access_same_token(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    owner = make_user(db_session, role="OWNER")
    viewer = make_user(db_session, role="VIEWER")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    grant_permission(
        db_session, document=doc, user=viewer, permission="READ", granted_by=owner
    )
    viewer_headers = auth_header(viewer, auth_settings)
    owner_headers = auth_header(owner, auth_settings)

    assert client.get(f"/documents/{doc.id}", headers=viewer_headers).status_code == 200
    assert (
        client.get(f"/documents/{doc.id}/download", headers=viewer_headers).status_code
        == 200
    )

    revoke = client.delete(
        f"/documents/{doc.id}/permissions/{viewer.id}",
        headers=owner_headers,
    )
    assert revoke.status_code == 200

    storage_mock.open_object.reset_mock()
    assert client.get(f"/documents/{doc.id}", headers=viewer_headers).status_code == 404
    assert (
        client.get(f"/documents/{doc.id}/download", headers=viewer_headers).status_code
        == 404
    )
    storage_mock.open_object.assert_not_called()


def test_forged_ids_and_bodies_do_not_bypass_authorisation(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    owner = make_user(db_session, role="OWNER")
    attacker = make_user(db_session, role="VIEWER")
    admin = make_user(db_session, role="ADMIN")
    doc = make_document(db_session, owner)
    storage_mock._store[doc.storage_key] = DOCX_BYTES
    attacker_headers = auth_header(attacker, auth_settings)

    # Guessed / forged document ID.
    forged_id = uuid.uuid4()
    assert (
        client.get(f"/documents/{forged_id}", headers=attacker_headers).status_code
        == 404
    )
    assert (
        client.get(
            f"/documents/{forged_id}/download",
            headers=attacker_headers,
        ).status_code
        == 404
    )

    # Client-supplied owner_id / storage_key / role on metadata PATCH.
    assert (
        client.patch(
            f"/documents/{doc.id}",
            headers=attacker_headers,
            json={
                "title": "Nope",
                "owner_id": str(attacker.id),
                "storage_key": "evil/key",
                "role": "OWNER",
            },
        ).status_code
        in {404, 422}
    )

    # Admin without grant cannot read contents.
    admin_headers = auth_header(admin, auth_settings)
    assert client.get(f"/documents/{doc.id}", headers=admin_headers).status_code == 404
    assert (
        client.get(f"/documents/{doc.id}/download", headers=admin_headers).status_code
        == 404
    )

    # Platform VIEWER cannot upload.
    assert (
        client.post(
            "/documents",
            headers=attacker_headers,
            data={"title": "X", "category": "Y"},
            files={
                "file": (
                    "x.docx",
                    DOCX_BYTES,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        ).status_code
        == 403
    )

    # Owner still owns the document; attacker did not become owner.
    db_session.refresh(doc)
    assert doc.owner_id == owner.id
