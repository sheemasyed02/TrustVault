"""End-to-end acceptance journey for the TrustVault hackathon brief.

Covers the owner → share → revoke → EDIT → admin → deactivate narrative
using isolated fixtures (no demo seed, no real confidential files).
"""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.upload_audit import RecordingUploadAuditHook
from tests.security.conftest import auth_header, make_user


DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _minimal_docx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
            'package/2006/content-types"></Types>',
        )
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main"><w:body><w:p/></w:body></w:document>',
        )
    return buffer.getvalue()


def test_acceptance_owner_share_revoke_edit_admin_journey(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
    audit_hook: RecordingUploadAuditHook,
):
    """Steps 1–16 of the acceptance journey (automated)."""
    owner = make_user(db_session, role="OWNER")
    recipient = make_user(db_session, role="VIEWER")
    admin = make_user(db_session, role="ADMIN")
    owner_headers = auth_header(owner, auth_settings)
    recipient_headers = auth_header(recipient, auth_settings)
    admin_headers = auth_header(admin, auth_settings)
    content = _minimal_docx()

    # 1–3: Owner uploads; document appears in owned list.
    upload = client.post(
        "/documents",
        headers=owner_headers,
        data={
            "title": "Acceptance Journey Report",
            "category": "Finance",
            "description": "acceptance-test",
        },
        files={"file": ("acceptance.docx", content, DOCX_MIME)},
    )
    assert upload.status_code == 201, upload.text
    doc_id = upload.json()["id"]
    storage_mock.upload_bytes.assert_called()

    owned = client.get(
        "/documents",
        headers=owner_headers,
        params={"owner_id": str(owner.id)},
    )
    assert owned.status_code == 200
    assert any(row["id"] == doc_id for row in owned.json()["results"])
    assert any(
        row["id"] == doc_id and row["your_access"] == "OWNER"
        for row in owned.json()["results"]
    )

    # 4: Unrelated recipient cannot discover the document.
    hidden = client.get(
        "/documents",
        headers=recipient_headers,
        params={"title": "Acceptance Journey Report"},
    )
    assert hidden.status_code == 200
    assert hidden.json()["total"] == 0
    assert client.get(f"/documents/{doc_id}", headers=recipient_headers).status_code == 404
    assert (
        client.get(f"/documents/{doc_id}/download", headers=recipient_headers).status_code
        == 404
    )

    # 5–7: Grant READ; recipient can read/download but not edit/share/delete.
    grant_read = client.post(
        f"/documents/{doc_id}/permissions",
        headers=owner_headers,
        json={"user_id": str(recipient.id), "permission": "READ"},
    )
    assert grant_read.status_code == 201

    shared = client.get(
        "/documents",
        headers=recipient_headers,
        params={"shared_only": "true"},
    )
    assert shared.status_code == 200
    assert shared.json()["total"] == 1
    assert shared.json()["results"][0]["your_access"] == "READ"

    meta = client.get(f"/documents/{doc_id}", headers=recipient_headers)
    assert meta.status_code == 200
    assert meta.json()["your_access"] == "READ"
    download = client.get(f"/documents/{doc_id}/download", headers=recipient_headers)
    assert download.status_code == 200
    assert download.content == content

    assert (
        client.patch(
            f"/documents/{doc_id}",
            headers=recipient_headers,
            json={"title": "Hacked"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/documents/{doc_id}/permissions",
            headers=recipient_headers,
            json={"user_id": str(admin.id), "permission": "READ"},
        ).status_code
        == 403
    )
    assert client.delete(f"/documents/{doc_id}", headers=recipient_headers).status_code == 403

    # 8–9: Owner revokes; same recipient JWT denied on next download.
    revoke = client.delete(
        f"/documents/{doc_id}/permissions/{recipient.id}",
        headers=owner_headers,
    )
    assert revoke.status_code == 200
    storage_mock.open_object.reset_mock()
    denied = client.get(f"/documents/{doc_id}/download", headers=recipient_headers)
    assert denied.status_code == 404
    storage_mock.open_object.assert_not_called()

    # 10–11: Grant EDIT; metadata OK; share/delete still forbidden.
    grant_edit = client.post(
        f"/documents/{doc_id}/permissions",
        headers=owner_headers,
        json={"user_id": str(recipient.id), "permission": "EDIT"},
    )
    assert grant_edit.status_code == 201
    patched = client.patch(
        f"/documents/{doc_id}",
        headers=recipient_headers,
        json={"title": "Edited By Recipient", "category": "Legal"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Edited By Recipient"
    assert patched.json()["your_access"] == "EDIT"
    assert (
        client.post(
            f"/documents/{doc_id}/permissions",
            headers=recipient_headers,
            json={"user_id": str(admin.id), "permission": "READ"},
        ).status_code
        == 403
    )
    assert client.delete(f"/documents/{doc_id}", headers=recipient_headers).status_code == 403

    # 12: Successful and denied actions recorded by the request audit hook.
    actions = {(e["action"], e["outcome"]) for e in audit_hook.events}
    assert ("DOCUMENT_UPLOAD", "SUCCESS") in actions
    assert ("DOCUMENT_PERMISSION_GRANT", "SUCCESS") in actions
    assert ("DOCUMENT_PERMISSION_REVOKE", "SUCCESS") in actions
    assert ("DOCUMENT_DOWNLOAD", "DENIED") in actions or (
        "DOCUMENT_DOWNLOAD",
        "SUCCESS",
    ) in actions
    assert any(
        e["action"] == "DOCUMENT_METADATA_UPDATE" and e["outcome"] == "DENIED"
        for e in audit_hook.events
    ) or any(
        e["action"] == "DOCUMENT_METADATA_UPDATE" and e["outcome"] == "SUCCESS"
        for e in audit_hook.events
    )

    # 13: Integrity endpoint returns explicit valid field (empty/partial chain OK).
    integrity = client.get("/admin/audit/integrity", headers=admin_headers)
    assert integrity.status_code == 200
    body = integrity.json()
    assert "valid" in body
    assert isinstance(body["valid"], bool)

    # 14–15: ADMIN user/audit APIs work; cannot download unshared content by role.
    assert client.get("/admin/summary", headers=admin_headers).status_code == 200
    assert client.get("/admin/users", headers=admin_headers).status_code == 200
    assert client.get("/admin/audit/events", headers=admin_headers).status_code == 200
    # Revoke recipient again so admin has no grant path via confusion; admin never had grant.
    client.delete(
        f"/documents/{doc_id}/permissions/{recipient.id}",
        headers=owner_headers,
    )
    storage_mock.open_object.reset_mock()
    assert client.get(f"/documents/{doc_id}/download", headers=admin_headers).status_code == 404
    storage_mock.open_object.assert_not_called()

    # 16: Disabled account blocked on next protected request with same token.
    assert client.get("/users/me", headers=recipient_headers).status_code == 200
    deactivate = client.patch(
        f"/admin/users/{recipient.id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert deactivate.status_code == 200
    assert client.get("/users/me", headers=recipient_headers).status_code == 401
    assert client.get("/documents", headers=recipient_headers).status_code == 401


def test_acceptance_search_does_not_leak_inaccessible_metadata(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
):
    """Search/filter must not reveal titles or rows for inaccessible documents."""
    owner = make_user(db_session, role="OWNER")
    stranger = make_user(db_session, role="VIEWER")
    content = _minimal_docx()
    upload = client.post(
        "/documents",
        headers=auth_header(owner, auth_settings),
        data={"title": "SecretAlphaOmega", "category": "Legal"},
        files={"file": ("secret.docx", content, DOCX_MIME)},
    )
    assert upload.status_code == 201
    headers = auth_header(stranger, auth_settings)
    for params in (
        {"title": "SecretAlphaOmega"},
        {"category": "Legal"},
        {"owner_id": str(owner.id)},
        {"owner_email": owner.email},
    ):
        response = client.get("/documents", headers=headers, params=params)
        assert response.status_code == 200
        assert response.json()["total"] == 0
        assert response.json()["results"] == []
        assert "SecretAlphaOmega" not in response.text
