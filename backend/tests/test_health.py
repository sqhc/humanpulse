from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "humanpulse-api"
    assert body["version"]


def test_root_points_to_docs_and_health() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["health"] == "/api/v1/health"


def test_openapi_contains_health_paths() -> None:
    schema = app.openapi()
    assert "/api/v1/health" in schema["paths"]
    assert "/api/v1/ready" in schema["paths"]
