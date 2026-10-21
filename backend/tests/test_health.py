"""Smoke tests for the scaffold FastAPI health endpoint."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "TrustVault"


def test_unknown_route_returns_not_found():
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"
