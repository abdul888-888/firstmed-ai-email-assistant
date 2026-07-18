"""Tests for the template repository + API (Phase 7)."""

from __future__ import annotations

from app.repositories.template import TemplateRepository


async def _seed(db_session):
    repo = TemplateRepository(db_session)
    await repo.upsert(
        key="office_hours", title="Office hours", category="front_office", body="Mon-Fri 8-8."
    )
    await repo.upsert(
        key="booking_link", title="Booking link", category="scheduling", body="Book: http://x"
    )
    await repo.upsert(
        key="old_hours", title="Old hours", category="front_office", body="stale", is_active=False
    )
    return repo


# --- repository ------------------------------------------------------------


async def test_repo_upsert_is_idempotent_by_key(db_session):
    repo = TemplateRepository(db_session)
    a = await repo.upsert(key="k", title="One", category="general", body="b1")
    b = await repo.upsert(key="k", title="Two", category="general", body="b2")
    assert a.id == b.id and b.title == "Two" and b.body == "b2"


async def test_repo_list_active_and_by_category(db_session):
    await _seed(db_session)
    repo = TemplateRepository(db_session)

    active = await repo.list()
    assert {t.key for t in active} == {"office_hours", "booking_link"}  # inactive excluded

    fo = await repo.list(category="front_office")
    assert [t.key for t in fo] == ["office_hours"]

    incl_inactive = await repo.list(active_only=False)
    assert len(incl_inactive) == 3


# --- API -------------------------------------------------------------------


async def _auth_token(client, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "T", "role": "front_office"},
    )
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login.json()["access_token"]


async def test_templates_status(client):
    resp = await client.get("/api/v1/templates/status")
    assert resp.status_code == 200
    assert resp.json() == {"module": "templates", "implemented": True, "phase": 7}


async def test_list_templates_requires_auth(client):
    assert (await client.get("/api/v1/templates")).status_code == 401


async def test_list_templates(client, db_session):
    await _seed(db_session)
    token = await _auth_token(client, "tpl@firstmed.com")
    h = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/templates", headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    keys = {t["key"] for t in body["templates"]}
    assert keys == {"office_hours", "booking_link"}
    assert all("body" in t and "category" in t for t in body["templates"])

    # category filter
    fo = await client.get("/api/v1/templates?category=front_office", headers=h)
    assert [t["key"] for t in fo.json()["templates"]] == ["office_hours"]

    # include inactive
    allt = await client.get("/api/v1/templates?active=false", headers=h)
    assert allt.json()["count"] == 3


async def test_get_template_404(client):
    token = await _auth_token(client, "tpl404@firstmed.com")
    resp = await client.get(
        "/api/v1/templates/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
