"""List API returns your_access and supports shared_only filtering."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from tests.security.conftest import (
    auth_header,
    grant_permission,
    make_document,
    make_user,
)


def test_list_includes_your_access_for_owner_read_edit(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = make_user(db_session, role="OWNER")
    reader = make_user(db_session, role="VIEWER")
    editor = make_user(db_session, role="VIEWER")
    owned = make_document(db_session, owner, title="Owned Doc")
    shared_read = make_document(db_session, owner, title="Shared Read")
    shared_edit = make_document(db_session, owner, title="Shared Edit")
    grant_permission(
        db_session,
        document=shared_read,
        user=reader,
        permission="READ",
        granted_by=owner,
    )
    grant_permission(
        db_session,
        document=shared_edit,
        user=editor,
        permission="EDIT",
        granted_by=owner,
    )

    owner_list = client.get("/documents", headers=auth_header(owner, auth_settings))
    assert owner_list.status_code == 200
    by_id = {row["id"]: row for row in owner_list.json()["results"]}
    assert by_id[str(owned.id)]["your_access"] == "OWNER"

    read_list = client.get("/documents", headers=auth_header(reader, auth_settings))
    assert read_list.status_code == 200
    read_rows = read_list.json()["results"]
    assert len(read_rows) == 1
    assert read_rows[0]["id"] == str(shared_read.id)
    assert read_rows[0]["your_access"] == "READ"

    edit_list = client.get("/documents", headers=auth_header(editor, auth_settings))
    assert edit_list.status_code == 200
    edit_rows = edit_list.json()["results"]
    assert len(edit_rows) == 1
    assert edit_rows[0]["your_access"] == "EDIT"


def test_shared_only_excludes_owned_documents(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = make_user(db_session, role="OWNER")
    viewer = make_user(db_session, role="VIEWER")
    owned = make_document(db_session, owner, title="Mine")
    shared = make_document(db_session, owner, title="Shared")
    grant_permission(
        db_session,
        document=shared,
        user=viewer,
        permission="READ",
        granted_by=owner,
    )
    # Owner also receives a grant on nothing extra; viewer should only see shared.
    headers = auth_header(viewer, auth_settings)
    response = client.get(
        "/documents",
        headers=headers,
        params={"shared_only": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["id"] == str(shared.id)
    assert body["results"][0]["your_access"] == "READ"
    assert str(owned.id) not in {row["id"] for row in body["results"]}


def test_shared_only_rejects_owner_id_combo(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    owner = make_user(db_session, role="OWNER")
    response = client.get(
        "/documents",
        headers=auth_header(owner, auth_settings),
        params={"shared_only": "true", "owner_id": str(owner.id)},
    )
    assert response.status_code == 422
