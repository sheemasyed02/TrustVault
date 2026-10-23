"""Smoke tests for liveness and readiness endpoints."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "TrustVault"
    assert "database" not in payload
    assert "DATABASE_URL" not in response.text


def test_readiness_reports_database_without_secrets():
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code in {200, 503}
    payload = response.json()
    assert payload["service"] == "TrustVault"
    assert "checks" in payload
    assert isinstance(payload["checks"]["database"], bool)
    assert "postgresql" not in response.text.lower()
    assert "password" not in response.text.lower()
    assert "@" not in response.text


def test_unknown_route_returns_not_found():
    with TestClient(app) as client:
        response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"
