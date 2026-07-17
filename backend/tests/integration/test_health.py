"""Integration tests for health endpoints."""

from __future__ import annotations


async def test_liveness(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"]
    assert body["version"]


async def test_readiness_reports_database_ok(client):
    # Redis is not running in the test environment, so overall readiness may be
    # 503, but the database check must pass (overridden to SQLite).
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert body["checks"]["database"] == "ok"
    assert "redis" in body["checks"]


async def test_root_redirects_to_docs(client):
    resp = await client.get("/", follow_redirects=False)
    assert resp.status_code in (307, 308)
    assert resp.headers["location"] == "/docs"


async def test_module_placeholder_status(client):
    # Healzz is still a placeholder (Phase 10); gmail/notion are implemented.
    resp = await client.get("/api/v1/healzz/status")
    assert resp.status_code == 200
    assert resp.json() == {"module": "healzz", "implemented": False, "phase": 10}
