"""Authenticated GET /users/search tests — share-recipient directory lookup."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import User
from app.db.session import get_db, reset_engine
from app.main import app
from app.services.user_search import escape_like_pattern

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

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: auth_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _user(
    session: Session,
    *,
    name: str,
    email: str,
    role: str = "VIEWER",
    is_active: bool = True,
) -> User:
    user = User(
        name=name,
        email=email.lower(),
        password_hash=hash_password("search-password-12"),
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user


def _auth(user: User, settings: Settings) -> dict[str, str]:
    token, _ = create_access_token(subject_user_id=user.id, settings=settings)
    return {"Authorization": f"Bearer {token}"}


def test_unauthenticated_search_rejected(client: TestClient):
    response = client.get("/users/search", params={"q": "bob"})
    assert response.status_code == 401


def test_empty_and_short_query_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    actor = _user(db_session, name="Alice", email=f"alice-{uuid.uuid4()}@ex.com", role="OWNER")
    headers = _auth(actor, auth_settings)

    empty = client.get("/users/search", params={"q": ""}, headers=headers)
    assert empty.status_code == 422

    short = client.get("/users/search", params={"q": "a"}, headers=headers)
    assert short.status_code == 422
    assert "at least 2" in short.json()["detail"].lower()

    whitespace = client.get("/users/search", params={"q": "  "}, headers=headers)
    assert whitespace.status_code == 422


def test_search_matches_name_and_email_excludes_self_and_inactive(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    alice = _user(
        db_session,
        name="Alice Owner",
        email=f"alice-{uuid.uuid4()}@ex.com",
        role="OWNER",
    )
    bob = _user(
        db_session,
        name="Bob Viewer",
        email=f"bob.unique-{uuid.uuid4()}@example.com",
        role="VIEWER",
    )
    inactive = _user(
        db_session,
        name="Bob Inactive",
        email=f"bob.inactive-{uuid.uuid4()}@example.com",
        role="VIEWER",
        is_active=False,
    )
    carol = _user(
        db_session,
        name="Carol Admin",
        email=f"carol-{uuid.uuid4()}@ex.com",
        role="ADMIN",
    )
    headers = _auth(alice, auth_settings)

    by_email = client.get(
        "/users/search",
        params={"q": bob.email.split("@")[0]},
        headers=headers,
    )
    assert by_email.status_code == 200
    body = by_email.json()
    ids = {item["id"] for item in body["results"]}
    assert str(bob.id) in ids
    assert str(alice.id) not in ids
    assert str(inactive.id) not in ids
    bob_hit = next(item for item in body["results"] if item["id"] == str(bob.id))
    assert bob_hit["name"] == "Bob Viewer"
    assert bob_hit["email"] == bob.email
    assert set(bob_hit.keys()) == {"id", "name", "email"}
    assert "password_hash" not in by_email.text
    assert "role" not in bob_hit
    assert "is_active" not in bob_hit
    assert "created_at" not in bob_hit

    by_name = client.get(
        "/users/search",
        params={"q": "Carol"},
        headers=headers,
    )
    assert by_name.status_code == 200
    name_ids = {item["id"] for item in by_name.json()["results"]}
    assert str(carol.id) in name_ids
    assert str(alice.id) not in name_ids


def test_search_is_case_insensitive(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    actor = _user(db_session, name="Searcher", email=f"s-{uuid.uuid4()}@ex.com", role="OWNER")
    target = _user(
        db_session,
        name="Mixed Case Person",
        email=f"mixed-{uuid.uuid4()}@ex.com",
    )
    response = client.get(
        "/users/search",
        params={"q": "mixed case"},
        headers=_auth(actor, auth_settings),
    )
    assert response.status_code == 200
    assert str(target.id) in {item["id"] for item in response.json()["results"]}


def test_search_by_exact_user_uuid(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    actor = _user(db_session, name="Owner", email=f"o-{uuid.uuid4()}@ex.com", role="OWNER")
    target = _user(
        db_session,
        name="Exact Id User",
        email=f"exact-{uuid.uuid4()}@ex.com",
    )
    response = client.get(
        "/users/search",
        params={"q": str(target.id)},
        headers=_auth(actor, auth_settings),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["id"] == str(target.id)


def test_exclude_user_id_omits_document_owner(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    actor = _user(db_session, name="Actor", email=f"a-{uuid.uuid4()}@ex.com", role="OWNER")
    owner = _user(db_session, name="Doc Owner", email=f"owner-{uuid.uuid4()}@ex.com", role="OWNER")
    viewer = _user(
        db_session,
        name="Shared Marker User",
        email=f"marker-{uuid.uuid4()}@ex.com",
    )
    headers = _auth(actor, auth_settings)
    # Without exclude, both match "User" / marker differently — search by shared token.
    marker = viewer.email.split("@")[0]
    included = client.get(
        "/users/search",
        params={"q": marker},
        headers=headers,
    )
    assert included.status_code == 200
    assert str(viewer.id) in {item["id"] for item in included.json()["results"]}

    excluded = client.get(
        "/users/search",
        params={"q": "Doc Owner", "exclude_user_id": str(owner.id)},
        headers=headers,
    )
    assert excluded.status_code == 200
    assert str(owner.id) not in {item["id"] for item in excluded.json()["results"]}


def test_like_metacharacters_are_literal(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    actor = _user(db_session, name="Actor", email=f"a-{uuid.uuid4()}@ex.com", role="OWNER")
    literal = _user(
        db_session,
        name="Percent 100%",
        email=f"pct-{uuid.uuid4()}@ex.com",
    )
    # Without escaping, "%" would match everyone.
    response = client.get(
        "/users/search",
        params={"q": "100%"},
        headers=_auth(actor, auth_settings),
    )
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["results"]}
    assert str(literal.id) in ids
    assert escape_like_pattern("100%") == r"100\%"


def test_pagination_bounds(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    actor = _user(db_session, name="Pager", email=f"p-{uuid.uuid4()}@ex.com", role="OWNER")
    marker = f"pageprobe-{uuid.uuid4().hex[:8]}"
    created = [
        _user(
            db_session,
            name=f"{marker} User {index:02d}",
            email=f"{marker}{index:02d}@ex.com",
        )
        for index in range(5)
    ]
    headers = _auth(actor, auth_settings)

    page1 = client.get(
        "/users/search",
        params={"q": marker, "page": 1, "page_size": 2},
        headers=headers,
    )
    assert page1.status_code == 200
    body1 = page1.json()
    assert body1["total"] == 5
    assert body1["page"] == 1
    assert body1["page_size"] == 2
    assert body1["total_pages"] == 3
    assert len(body1["results"]) == 2

    page2 = client.get(
        "/users/search",
        params={"q": marker, "page": 2, "page_size": 2},
        headers=headers,
    )
    assert page2.status_code == 200
    body2 = page2.json()
    assert len(body2["results"]) == 2
    assert {item["id"] for item in body1["results"]}.isdisjoint(
        {item["id"] for item in body2["results"]}
    )

    oversized = client.get(
        "/users/search",
        params={"q": marker, "page_size": 100},
        headers=headers,
    )
    assert oversized.status_code == 422

    # Ensure created users are referenced so flake detection is clear.
    assert len(created) == 5


def test_no_results_returns_empty_list(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
):
    actor = _user(db_session, name="Alone", email=f"alone-{uuid.uuid4()}@ex.com", role="OWNER")
    response = client.get(
        "/users/search",
        params={"q": "zzznomatchxyz"},
        headers=_auth(actor, auth_settings),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []
    assert body["total"] == 0
    assert body["total_pages"] == 0
