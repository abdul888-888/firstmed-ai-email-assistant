"""API tests for the Notion integration endpoints."""

from __future__ import annotations

from app.core.config import settings


async def _auth_token(client, email: str = "n@firstmed.com") -> str:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "supersecret1",
            "full_name": "N",
            "role": "front_office",
        },
    )
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login.json()["access_token"]


async def test_notion_status_reports_implemented(client):
    resp = await client.get("/api/v1/notion/status")
    assert resp.status_code == 200
    assert resp.json() == {"module": "notion", "implemented": True, "phase": 3}


async def test_notion_search_requires_auth(client):
    resp = await client.get("/api/v1/notion/search")
    assert resp.status_code == 401


async def test_notion_search_not_configured(client):
    token = await _auth_token(client)
    resp = await client.get("/api/v1/notion/search", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 503


async def test_notion_connection_not_configured(client):
    token = await _auth_token(client)
    resp = await client.get(
        "/api/v1/notion/connection", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["configured"] is False


async def test_notion_search_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "notion_api_key", "secret_test_token")
    token = await _auth_token(client)

    # Patch the service call so no real network is used.
    from app.services.notion_service import NotionService

    async def fake_search(self, query=None, *, page_size=25):
        return {
            "results": [
                {
                    "id": "p1",
                    "object": "page",
                    "title": "Triage SOP",
                    "url": "https://notion.so/p1",
                    "last_edited_time": "",
                }
            ],
            "next_cursor": None,
            "has_more": False,
        }

    monkeypatch.setattr(NotionService, "search", fake_search)

    resp = await client.get(
        "/api/v1/notion/search?q=sop", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"][0]["title"] == "Triage SOP"
    assert body["has_more"] is False
