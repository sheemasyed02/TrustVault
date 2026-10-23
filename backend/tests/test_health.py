"""Smoke tests for liveness and readiness endpoints."""

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app, create_app


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


def test_production_hides_openapi_docs(monkeypatch):
    """Production must not expose /docs, /redoc, or /openapi.json."""
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        prod_app = create_app()
        with TestClient(prod_app) as client:
            assert client.get("/docs").status_code == 404
            assert client.get("/redoc").status_code == 404
            assert client.get("/openapi.json").status_code == 404
            assert client.get("/health").status_code == 200
    finally:
        get_settings.cache_clear()


def test_unknown_route_returns_not_found():
    with TestClient(app) as client:
        response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"
