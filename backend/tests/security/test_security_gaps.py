"""Additional security gap regressions not covered only by the matrix."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import create_app
from app.services.document_download import safe_download_filename
from app.services.file_validation import normalize_extension, FileValidationError
from tests.security.conftest import auth_header, make_document, make_user
import pytest


def test_cors_does_not_allow_wildcard_by_default():
    """CORS origins come from config; default must not be '*'."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    # Settings requires DATABASE_URL from env; use the loaded test .env.
    settings = get_settings()
    origins = settings.cors_origin_list
    assert "*" not in origins
    assert all(o.startswith("http://") or o.startswith("https://") for o in origins)


def test_r2_storage_service_has_no_public_or_presigned_url_helpers():
    from app.storage import R2StorageService

    forbidden = {
        "generate_presigned_url",
        "presigned_url",
        "get_public_url",
        "public_url",
        "make_public",
    }
    methods = {name for name in dir(R2StorageService) if not name.startswith("_")}
    assert forbidden.isdisjoint(methods)


def test_upload_filename_path_segments_stripped():
    ext = normalize_extension("../../evil/../secret.docx")
    assert ext == ".docx"
    with pytest.raises(FileValidationError):
        normalize_extension("../../evil.exe")


def test_safe_download_filename_neutralizes_header_injection(db_session: Session):
    owner = make_user(db_session, role="OWNER")
    doc = make_document(db_session, owner)
    doc.original_filename = 'report\r\nSet-Cookie: x=1".docx'
    db_session.flush()
    name = safe_download_filename(doc)
    # Header injection requires CR/LF or quote breaks — those must be gone.
    assert "\r" not in name
    assert "\n" not in name
    assert '"' not in name
    assert name.endswith(".docx")


def test_login_failure_does_not_echo_password(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    user = make_user(db_session, role="OWNER", email=f"login-gap-{__import__('uuid').uuid4()}@example.com")
    secret = "security-matrix-password-12-WRONG"
    response = client.post(
        "/auth/login",
        json={"email": user.email, "password": secret},
    )
    assert response.status_code == 401
    body = response.text
    assert secret not in body
    assert "password_hash" not in body
