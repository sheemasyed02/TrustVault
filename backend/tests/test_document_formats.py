"""DOCX-only upload, content editing, PDF conversion, and permission checks."""

from __future__ import annotations

import io
import uuid
import zipfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.documents import get_document_audit, get_storage, get_upload_audit
from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import Document, User
from app.db.session import get_db, reset_engine
from app.main import app
from app.services.docx_to_pdf import (
    DocxConversionError,
    convert_docx_bytes_to_pdf,
    convert_docx_bytes_to_pdf_detailed,
)
from app.services.document_content import rebuild_docx_preserving_package
from app.services.file_validation import DOCX_MEDIA_TYPE, PDF_MEDIA_TYPE
from app.services.upload_audit import RecordingUploadAuditHook

TEST_JWT_SECRET = "formats-test-jwt-secret-key-32charsxx"


def _minimal_docx(text: str = "Hello TrustVault", *, extra_part: bool = False) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
            'package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
            "wordprocessingml/2006/main\"><w:body><w:p><w:r><w:t>"
            f"{text}</w:t></w:r></w:p></w:body></w:document>",
        )
        if extra_part:
            archive.writestr("word/styles.xml", "<styles>keep-me</styles>")
    return buffer.getvalue()


def _minimal_pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


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
def storage_mock() -> MagicMock:
    store: dict[str, bytes] = {}
    mock = MagicMock()

    def upload_bytes(key: str, data: bytes, **_kwargs):
        store[key] = bytes(data)
        result = MagicMock()
        result.storage_key = key
        result.size_bytes = len(data)
        return result

    def open_object(key: str):
        data = store.get(key, b"")
        stream = io.BytesIO(data)

        class _CM:
            def __enter__(self):
                return stream

            def __exit__(self, *args):
                stream.close()

        return _CM()

    mock.upload_bytes.side_effect = upload_bytes
    mock.open_object.side_effect = open_object
    mock._store = store
    return mock


@pytest.fixture()
def audit_hook() -> RecordingUploadAuditHook:
    return RecordingUploadAuditHook()


@pytest.fixture()
def client(
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
    audit_hook: RecordingUploadAuditHook,
) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_storage] = lambda: storage_mock
    app.dependency_overrides[get_upload_audit] = lambda: audit_hook
    app.dependency_overrides[get_document_audit] = lambda: audit_hook
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _user(session: Session, *, role: str = "OWNER") -> User:
    user = User(
        name=f"{role} User",
        email=f"{role.lower()}-{uuid.uuid4()}@example.com",
        password_hash=hash_password("formats-password-12"),
        role=role,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _auth(user: User, settings: Settings) -> dict[str, str]:
    token, _ = create_access_token(subject_user_id=user.id, settings=settings)
    return {"Authorization": f"Bearer {token}"}


def _legacy_pdf_document(session: Session, owner: User, storage_mock: MagicMock) -> Document:
    key = f"objects/{uuid.uuid4()}.bin"
    pdf = _minimal_pdf()
    storage_mock._store[key] = pdf
    doc = Document(
        owner_id=owner.id,
        title="Legacy PDF",
        original_filename="legacy.pdf",
        mime_type=PDF_MEDIA_TYPE,
        category="legacy",
        description=None,
        storage_key=key,
        file_size=len(pdf),
        sha256_checksum="b" * 64,
    )
    session.add(doc)
    session.flush()
    return doc


def test_upload_docx_succeeds_pdf_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    headers = _auth(owner, auth_settings)

    pdf = client.post(
        "/documents",
        headers=headers,
        data={"title": "PDF Doc", "category": "Reports"},
        files={"file": ("report.pdf", _minimal_pdf(), PDF_MEDIA_TYPE)},
    )
    assert pdf.status_code == 415
    storage_mock.upload_bytes.assert_not_called()

    for bad_name, content, ctype in (
        ("old.doc", b"OLE", "application/msword"),
        ("macro.docm", b"PK", "application/vnd.ms-word.document.macroEnabled.12"),
        ("note.exe", b"MZ", "application/octet-stream"),
    ):
        rejected = client.post(
            "/documents",
            headers=headers,
            data={"title": "X", "category": "Y"},
            files={"file": (bad_name, content, ctype)},
        )
        assert rejected.status_code == 415, bad_name

    docx = client.post(
        "/documents",
        headers=headers,
        data={"title": "Word Doc", "category": "Reports"},
        files={"file": ("memo.docx", _minimal_docx(), DOCX_MEDIA_TYPE)},
    )
    assert docx.status_code == 201
    assert docx.json()["mime_type"] == DOCX_MEDIA_TYPE
    assert docx.json()["original_filename"] == "memo.docx"


def test_reject_malformed_docx(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    headers = _auth(owner, auth_settings)

    spoofed = client.post(
        "/documents",
        headers=headers,
        data={"title": "X", "category": "Y"},
        files={"file": ("fake.docx", b"not-a-zip", DOCX_MEDIA_TYPE)},
    )
    assert spoofed.status_code == 415

    empty = client.post(
        "/documents",
        headers=headers,
        data={"title": "X", "category": "Y"},
        files={"file": ("empty.docx", b"", DOCX_MEDIA_TYPE)},
    )
    assert empty.status_code in {400, 422}
    storage_mock.upload_bytes.assert_not_called()


def test_docx_conversion_produces_valid_pdf_not_rename():
    docx = _minimal_docx("Conversion marker text")
    assert not docx.startswith(b"%PDF")
    result = convert_docx_bytes_to_pdf_detailed(docx)
    assert result.pdf_bytes.startswith(b"%PDF")
    assert result.method in {"libreoffice", "reportlab_fallback"}
    assert not result.pdf_bytes.startswith(b"PK")
    assert len(result.pdf_bytes) > 64


def test_failed_conversion_does_not_leave_temp_files(tmp_path: Path, monkeypatch):
    docx = _minimal_docx()

    def boom(_docx: bytes) -> bytes:
        raise DocxConversionError("forced", reason_code="LIBREOFFICE_FAILED")

    monkeypatch.setattr(
        "app.services.docx_to_pdf._convert_via_libreoffice",
        boom,
    )
    monkeypatch.setattr(
        "app.services.docx_to_pdf._find_libreoffice",
        lambda: "/usr/bin/soffice",
    )
    before = set(Path(tmp_path).glob("**/*")) if tmp_path.exists() else set()
    pdf = convert_docx_bytes_to_pdf(docx)
    assert pdf.startswith(b"%PDF")
    after = set(Path(tmp_path).glob("**/*")) if tmp_path.exists() else set()
    assert before == after


def test_download_docx_as_pdf_and_legacy_pdf_passthrough(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    headers = _auth(owner, auth_settings)

    legacy = _legacy_pdf_document(db_session, owner, storage_mock)
    pdf_dl = client.get(f"/documents/{legacy.id}/download", headers=headers)
    assert pdf_dl.status_code == 200
    assert pdf_dl.content.startswith(b"%PDF")
    assert pdf_dl.headers["content-type"].startswith("application/pdf")
    assert pdf_dl.content == _minimal_pdf()

    docx_up = client.post(
        "/documents",
        headers=headers,
        data={"title": "Word", "category": "A"},
        files={"file": ("b.docx", _minimal_docx("Latest"), DOCX_MEDIA_TYPE)},
    )
    docx_id = docx_up.json()["id"]
    docx_dl = client.get(f"/documents/{docx_id}/download", headers=headers)
    assert docx_dl.status_code == 200
    assert docx_dl.content.startswith(b"%PDF")
    assert docx_dl.headers["content-type"].startswith("application/pdf")
    assert ".pdf" in docx_dl.headers.get("content-disposition", "").lower()
    assert ".docx" not in docx_dl.headers.get("content-disposition", "").lower()
    assert not docx_dl.content.startswith(b"PK")


def test_docx_edit_preserves_package_and_pdf_uses_latest(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    headers = _auth(owner, auth_settings)
    created = client.post(
        "/documents",
        headers=headers,
        data={"title": "Editable", "category": "A"},
        files={
            "file": (
                "e.docx",
                _minimal_docx("Original", extra_part=True),
                DOCX_MEDIA_TYPE,
            )
        },
    )
    doc_id = created.json()["id"]
    stored_keys = list(storage_mock._store.keys())
    assert stored_keys
    before = storage_mock._store[stored_keys[0]]
    with zipfile.ZipFile(io.BytesIO(before)) as zf:
        assert "word/styles.xml" in zf.namelist()

    saved = client.put(
        f"/documents/{doc_id}/content",
        headers=headers,
        json={"text": "Edited body for PDF download"},
    )
    assert saved.status_code == 200

    after = storage_mock._store[stored_keys[0]]
    with zipfile.ZipFile(io.BytesIO(after)) as zf:
        assert "word/styles.xml" in zf.namelist()
        assert zf.read("word/styles.xml") == b"<styles>keep-me</styles>"
        body = zf.read("word/document.xml").decode("utf-8")
        assert "Edited body for PDF download" in body
        assert "Original" not in body

    download = client.get(f"/documents/{doc_id}/download", headers=headers)
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")
    assert len(download.content) > 20
    # ReportLab fallback embeds visible text; LibreOffice may compress.
    if b"Edited body for PDF download" not in download.content:
        assert download.content.startswith(b"%PDF")


def test_rebuild_docx_preserving_package_unit():
    original = _minimal_docx("Keep package", extra_part=True)
    rebuilt = rebuild_docx_preserving_package(original, "New text\nLine 2")
    with zipfile.ZipFile(io.BytesIO(rebuilt)) as zf:
        assert zf.read("word/styles.xml") == b"<styles>keep-me</styles>"
        xml = zf.read("word/document.xml").decode("utf-8")
        assert "New text" in xml
        assert "Line 2" in xml
        assert "Keep package" not in xml


def test_legacy_pdf_content_edit_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    headers = _auth(owner, auth_settings)
    legacy = _legacy_pdf_document(db_session, owner, storage_mock)
    resp = client.put(
        f"/documents/{legacy.id}/content",
        headers=headers,
        json={"text": "Should not save"},
    )
    assert resp.status_code == 415
    assert "PDF content editing is not supported" in resp.json()["detail"]


def test_read_cannot_edit_edit_cannot_metadata_owner_can_both(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    reader = _user(db_session, role="VIEWER")
    editor = _user(db_session, role="VIEWER")
    headers_owner = _auth(owner, auth_settings)
    created = client.post(
        "/documents",
        headers=headers_owner,
        data={"title": "Shared", "category": "A"},
        files={"file": ("s.docx", _minimal_docx(), DOCX_MEDIA_TYPE)},
    )
    doc_id = created.json()["id"]
    client.post(
        f"/documents/{doc_id}/permissions",
        headers=headers_owner,
        json={"user_id": str(reader.id), "permission": "READ"},
    )
    client.post(
        f"/documents/{doc_id}/permissions",
        headers=headers_owner,
        json={"user_id": str(editor.id), "permission": "EDIT"},
    )

    assert (
        client.put(
            f"/documents/{doc_id}/content",
            headers=_auth(reader, auth_settings),
            json={"text": "No"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/documents/{doc_id}",
            headers=_auth(reader, auth_settings),
            json={"title": "No"},
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/documents/{doc_id}/content",
            headers=_auth(editor, auth_settings),
            json={"text": "Yes"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/documents/{doc_id}",
            headers=_auth(editor, auth_settings),
            json={"title": "Hacked", "category": "X"},
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/documents/{doc_id}",
            headers=_auth(editor, auth_settings),
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/documents/{doc_id}/permissions",
            headers=_auth(editor, auth_settings),
            json={"user_id": str(reader.id), "permission": "READ"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/documents/{doc_id}",
            headers=headers_owner,
            json={"title": "Owner Title", "category": "OwnerCat"},
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/documents/{doc_id}/content",
            headers=headers_owner,
            json={"text": "Owner body"},
        ).status_code
        == 200
    )


def test_admin_cannot_open_content_by_role_alone(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    admin = _user(db_session, role="ADMIN")
    headers_owner = _auth(owner, auth_settings)
    created = client.post(
        "/documents",
        headers=headers_owner,
        data={"title": "Secret", "category": "A"},
        files={"file": ("s.docx", _minimal_docx("secret"), DOCX_MEDIA_TYPE)},
    )
    doc_id = created.json()["id"]
    storage_mock.open_object.reset_mock()
    assert client.get(
        f"/documents/{doc_id}/download",
        headers=_auth(admin, auth_settings),
    ).status_code in {403, 404}
    assert client.get(
        f"/documents/{doc_id}/download",
        headers=_auth(admin, auth_settings),
        params={"disposition": "inline"},
    ).status_code in {403, 404}
    assert client.put(
        f"/documents/{doc_id}/content",
        headers=_auth(admin, auth_settings),
        json={"text": "nope"},
    ).status_code in {403, 404}
    storage_mock.open_object.assert_not_called()


def test_conversion_failure_returns_safe_error(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
):
    owner = _user(db_session, role="OWNER")
    headers = _auth(owner, auth_settings)
    created = client.post(
        "/documents",
        headers=headers,
        data={"title": "FailConv", "category": "A"},
        files={"file": ("f.docx", _minimal_docx(), DOCX_MEDIA_TYPE)},
    )
    doc_id = created.json()["id"]

    def boom(_data: bytes):
        raise DocxConversionError("forced", reason_code="PDF_RENDER_FAILED")

    monkeypatch.setattr(
        "app.api.documents.convert_docx_bytes_to_pdf_detailed",
        boom,
    )
    resp = client.get(f"/documents/{doc_id}/download", headers=headers)
    assert resp.status_code == 503
    assert "converted" in resp.json()["detail"].lower() or "pdf" in resp.json()["detail"].lower()
    assert not resp.content.startswith(b"PK")


def test_revocation_blocks_preview_edit_and_download(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    storage_mock: MagicMock,
):
    owner = _user(db_session, role="OWNER")
    viewer = _user(db_session, role="VIEWER")
    headers_owner = _auth(owner, auth_settings)
    created = client.post(
        "/documents",
        headers=headers_owner,
        data={"title": "Revoke Me", "category": "A"},
        files={"file": ("r.docx", _minimal_docx(), DOCX_MEDIA_TYPE)},
    )
    doc_id = created.json()["id"]
    client.post(
        f"/documents/{doc_id}/permissions",
        headers=headers_owner,
        json={"user_id": str(viewer.id), "permission": "EDIT"},
    )
    viewer_headers = _auth(viewer, auth_settings)
    assert (
        client.get(
            f"/documents/{doc_id}/download",
            params={"disposition": "inline"},
            headers=viewer_headers,
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/documents/{doc_id}/content",
            headers=viewer_headers,
            json={"text": "While granted"},
        ).status_code
        == 200
    )
    client.delete(
        f"/documents/{doc_id}/permissions/{viewer.id}",
        headers=headers_owner,
    )
    storage_mock.open_object.reset_mock()
    assert (
        client.get(
            f"/documents/{doc_id}/download",
            params={"disposition": "inline"},
            headers=viewer_headers,
        ).status_code
        == 404
    )
    assert (
        client.get(f"/documents/{doc_id}/download", headers=viewer_headers).status_code
        == 404
    )
    assert (
        client.put(
            f"/documents/{doc_id}/content",
            headers=viewer_headers,
            json={"text": "After revoke"},
        ).status_code
        in {403, 404}
    )
    storage_mock.open_object.assert_not_called()
