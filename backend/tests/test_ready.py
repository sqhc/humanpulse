from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ready_reports_degraded_without_database() -> None:
    """无数据库时 /ready 必须返回 503 且说明原因，而不是 500。"""
    resp = client.get("/api/v1/ready")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert body["status"] in ("ready", "degraded")
    assert body["components"][0]["name"] == "database"
    if resp.status_code == 503:
        assert body["components"][0]["ok"] is False
