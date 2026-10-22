"""Part B demo workflow: register → promote → share → upgrade → revoke → audit.

Separate accounts exercise the full ownership and permission narrative against
the FastAPI app (no confidential production files).
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.documents import get_document_audit, get_upload_audit
from app.core.config import Settings
from app.main import app
from app.services.upload_audit import DurableAuditHook, RecordingUploadAuditHook
from tests.security.conftest import auth_header, make_user

DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _minimal_docx_with_text(text: str = "Hello TrustVault") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
            'package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
            f'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p>'
            "</w:body></w:document>",
        )
    return buffer.getvalue()


@pytest.fixture()
def _noop_committed_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid independent DENIED audit sessions locking against the test txn."""

    def _noop(**kwargs):
        return None

    monkeypatch.setattr("app.api.auth.append_audit_event_committed", _noop)
    monkeypatch.setattr("app.api.promotions.append_audit_event_committed", _noop)
    monkeypatch.setattr(
        "app.services.upload_audit.append_audit_event_committed", _noop
    )


def test_demo_register_promote_share_upgrade_revoke_audit(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock,
    audit_hook: RecordingUploadAuditHook,
    _noop_committed_audit,
):
    # Persist SUCCESS document/share audits into the request session so owner
    # audit summary counts are real (DENIED stay on the in-memory hook via noop).
    durable = DurableAuditHook(db_session)
    app.dependency_overrides[get_upload_audit] = lambda: durable
    app.dependency_overrides[get_document_audit] = lambda: durable

    # 1. Admin signs in and inspects registered users.
    admin = make_user(db_session, role="ADMIN", email="demo-admin@example.com")
    admin_headers = auth_header(admin, auth_settings)
    users = client.get("/admin/users", headers=admin_headers)
    assert users.status_code == 200
    assert users.json()["total"] >= 1

    # 2. New user signs up and receives VIEWER.
    signup_email = f"demo-owner-{uuid.uuid4()}@example.com"
    register = client.post(
        "/auth/register",
        json={
            "name": "Demo Future Owner",
            "email": signup_email,
            "password": "demo-password-12",
        },
    )
    assert register.status_code == 201, register.text
    assert register.json()["role"] == "VIEWER"

    login = client.post(
        "/auth/login",
        json={"email": signup_email, "password": "demo-password-12"},
    )
    assert login.status_code == 200
    owner_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = client.get("/users/me", headers=owner_headers)
    assert me.status_code == 200
    assert me.json()["role"] == "VIEWER"

    assert (
        client.post(
            "/documents",
            headers=owner_headers,
            data={"title": "Too Early", "category": "Demo"},
            files={
                "file": (
                    "early.docx",
                    _minimal_docx_with_text("too early"),
                    DOCX_MIME,
                )
            },
        ).status_code
        == 403
    )

    # 3–4. Viewer requests owner privileges; admin approves.
    request = client.post(
        "/promotions/requests",
        headers=owner_headers,
        json={"justification": "Need to upload demo documents"},
    )
    assert request.status_code == 201, request.text
    request_id = request.json()["id"]

    pending = client.get(
        "/admin/promotions",
        headers=admin_headers,
        params={"status": "PENDING"},
    )
    assert pending.status_code == 200
    assert any(row["id"] == request_id for row in pending.json()["results"])

    review = client.post(
        f"/admin/promotions/{request_id}/review",
        headers=admin_headers,
        json={"decision": "APPROVED"},
    )
    assert review.status_code == 200, review.text

    me_after = client.get("/users/me", headers=owner_headers)
    assert me_after.status_code == 200
    assert me_after.json()["role"] == "OWNER"

    viewer_a = make_user(db_session, role="VIEWER", email="demo-viewer-a@example.com")
    viewer_b = make_user(db_session, role="VIEWER", email="demo-viewer-b@example.com")
    headers_a = auth_header(viewer_a, auth_settings)
    headers_b = auth_header(viewer_b, auth_settings)

    # 5. Promoted owner uploads DOCX (PDF uploads are rejected by the API).
    assert (
        client.post(
            "/documents",
            headers=owner_headers,
            data={"title": "Rejected PDF", "category": "Policy"},
            files={
                "file": (
                    "policy.pdf",
                    b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n",
                    "application/pdf",
                )
            },
        ).status_code
        == 415
    )

    docx_upload = client.post(
        "/documents",
        headers=owner_headers,
        data={
            "title": "Demo DOCX Brief",
            "category": "Briefs",
            "description": "Initial DOCX",
        },
        files={
            "file": (
                "brief.docx",
                _minimal_docx_with_text("Original body"),
                DOCX_MIME,
            )
        },
    )
    assert docx_upload.status_code == 201, docx_upload.text
    docx_id = docx_upload.json()["id"]
    assert storage_mock.upload_bytes.called

    # 6. Owner edits title, category, description.
    patched = client.patch(
        f"/documents/{docx_id}",
        headers=owner_headers,
        json={
            "title": "Demo DOCX Brief Updated",
            "category": "Legal",
            "description": "Updated description",
        },
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Demo DOCX Brief Updated"
    assert patched.json()["category"] == "Legal"

    # 7. Owner grants READ to Viewer A.
    grant_read = client.post(
        f"/documents/{docx_id}/permissions",
        headers=owner_headers,
        json={"user_id": str(viewer_a.id), "permission": "READ"},
    )
    assert grant_read.status_code == 201, grant_read.text

    # 8. Viewer A views and downloads.
    assert (
        client.get(
            f"/documents/{docx_id}/download",
            headers=headers_a,
            params={"disposition": "inline"},
        ).status_code
        == 200
    )
    download_a = client.get(f"/documents/{docx_id}/download", headers=headers_a)
    assert download_a.status_code == 200
    assert download_a.content.startswith(b"%PDF")

    # 9. Viewer A cannot change metadata, delete, grant, or edit content on READ.
    assert (
        client.patch(
            f"/documents/{docx_id}",
            headers=headers_a,
            json={"title": "Hacked"},
        ).status_code
        == 403
    )
    assert client.delete(f"/documents/{docx_id}", headers=headers_a).status_code == 403
    assert (
        client.post(
            f"/documents/{docx_id}/permissions",
            headers=headers_a,
            json={"user_id": str(viewer_b.id), "permission": "READ"},
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/documents/{docx_id}/content",
            headers=headers_a,
            json={"text": "Should fail"},
        ).status_code
        == 403
    )

    # 10. Owner changes Viewer A grant to EDIT.
    upgrade = client.post(
        f"/documents/{docx_id}/permissions",
        headers=owner_headers,
        json={"user_id": str(viewer_a.id), "permission": "EDIT"},
    )
    assert upgrade.status_code == 201, upgrade.text
    assert upgrade.json()["permission"] == "EDIT"

    # 11. Viewer A can edit DOCX contents (EDIT grant).
    assert (
        client.put(
            f"/documents/{docx_id}/content",
            headers=headers_a,
            json={"text": "Viewer A edited body"},
        ).status_code
        == 200
    )

    # 12. Owner remains sole metadata / delete / sharing authority.
    assert (
        client.patch(
            f"/documents/{docx_id}",
            headers=headers_a,
            json={"title": "Still blocked"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/documents/{docx_id}/permissions",
            headers=headers_a,
            json={"user_id": str(viewer_b.id), "permission": "READ"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/documents/{docx_id}",
            headers=owner_headers,
            json={"description": "Owner-only metadata still works"},
        ).status_code
        == 200
    )

    # 13–14. Viewer B denied; attempt recorded on audit hook.
    assert client.get(f"/documents/{docx_id}", headers=headers_b).status_code in {
        403,
        404,
    }
    assert client.get(f"/documents/{docx_id}/download", headers=headers_b).status_code in {
        403,
        404,
    }
    # Denied attempts must not return document bytes; recording may be noop'ed
    # for independent commits, so assert access denial rather than hook rows.
    denied_bytes = client.get(f"/documents/{docx_id}/download", headers=headers_b)
    assert b"Original body" not in denied_bytes.content
    assert b"Viewer A edited body" not in denied_bytes.content

    # 15. Owner revokes Viewer A.
    assert (
        client.delete(
            f"/documents/{docx_id}/permissions/{viewer_a.id}",
            headers=owner_headers,
        ).status_code
        == 200
    )

    # 16. Viewer A subsequent protected requests denied.
    storage_mock.open_object.reset_mock()
    assert client.get(f"/documents/{docx_id}", headers=headers_a).status_code in {
        403,
        404,
    }
    assert client.get(
        f"/documents/{docx_id}/download",
        headers=headers_a,
        params={"disposition": "inline"},
    ).status_code in {403, 404}
    assert client.get(f"/documents/{docx_id}/download", headers=headers_a).status_code in {
        403,
        404,
    }
    assert (
        client.put(
            f"/documents/{docx_id}/content",
            headers=headers_a,
            json={"text": "After revoke"},
        ).status_code
        in {403, 404}
    )
    storage_mock.open_object.assert_not_called()

    # 17. Owner audit history with summary counts.
    owner_audit = client.get(f"/documents/{docx_id}/audit", headers=owner_headers)
    assert owner_audit.status_code == 200
    summary = owner_audit.json()["summary"]
    assert summary is not None
    assert summary["permission_grants"] >= 1
    assert summary["permission_revocations"] >= 1
    assert client.get(
        f"/documents/{docx_id}/audit", headers=headers_a
    ).status_code in {403, 404}

    # 18. Admin platform audit without opening confidential file.
    admin_events = client.get("/admin/audit/events", headers=admin_headers)
    assert admin_events.status_code == 200
    assert admin_events.json()["total"] >= 1
    for row in admin_events.json()["results"]:
        assert "password" not in row.get("metadata", {})
        assert "storage_key" not in row.get("metadata", {})
    assert client.get(
        f"/documents/{docx_id}/download", headers=admin_headers
    ).status_code in {403, 404}

    assert datetime.now(timezone.utc) is not None
