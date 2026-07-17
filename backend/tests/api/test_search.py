"""API tests for the retrieval / search endpoints."""

from __future__ import annotations

from app.models.document import DocumentSource
from app.repositories.document import DocumentRepository

SEARCH = "/api/v1/search"


async def _auth_token(client, email: str = "s@firstmed.com") -> str:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "supersecret1",
            "full_name": "S",
            "role": "front_office",
        },
    )
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login.json()["access_token"]


async def _seed(db_session):
    repo = DocumentRepository(db_session)
    await repo.upsert(
        source=DocumentSource.gmail.value,
        source_id="g1",
        title="Prescription refill",
        content="prescription refill request",
        url="https://mail.google.com/x",
    )
    await repo.upsert(
        source=DocumentSource.notion.value,
        source_id="n1",
        title="Billing FAQ",
        content="invoice and billing",
    )


async def test_search_status(client):
    resp = await client.get(f"{SEARCH}/status")
    assert resp.status_code == 200
    assert resp.json() == {"module": "search", "implemented": True, "phase": 4}


async def test_search_requires_auth(client):
    resp = await client.get(f"{SEARCH}?q=refill")
    assert resp.status_code == 401


async def test_search_returns_ranked_hits(client, db_session):
    await _seed(db_session)
    token = await _auth_token(client)
    resp = await client.get(
        f"{SEARCH}?q=prescription", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "prescription"
    assert body["count"] == 1
    assert body["results"][0]["document"]["source_id"] == "g1"
    assert body["results"][0]["score"] > 0


async def test_search_source_filter_validation(client, db_session):
    token = await _auth_token(client)
    resp = await client.get(
        f"{SEARCH}?q=x&source=bogus", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 400


async def test_search_stats(client, db_session):
    await _seed(db_session)
    token = await _auth_token(client)
    resp = await client.get(f"{SEARCH}/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"total": 2, "gmail": 1, "notion": 1}


async def test_get_document_not_found(client):
    token = await _auth_token(client)
    resp = await client.get(
        f"{SEARCH}/documents/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_reindex_reports_skipped_sources(client):
    # No Gmail link + Notion unconfigured => both skipped, zero indexed.
    token = await _auth_token(client)
    resp = await client.post(f"{SEARCH}/reindex", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["gmail_indexed"] == 0
    assert body["notion_indexed"] == 0
    assert "gmail: not connected" in body["notes"]
    assert "notion: not configured" in body["notes"]
