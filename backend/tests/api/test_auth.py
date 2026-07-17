"""API tests for the authentication skeleton."""

from __future__ import annotations

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def _new_user(email: str = "front@firstmed.com"):
    return {
        "email": email,
        "password": "supersecret1",
        "full_name": "Front Desk",
        "role": "front_office",
    }


async def test_register_creates_user(client):
    resp = await client.post(REGISTER, json=_new_user())
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "front@firstmed.com"
    assert body["role"] == "front_office"
    assert body["is_active"] is True
    assert "id" in body
    assert "password" not in body
    assert "hashed_password" not in body


async def test_register_duplicate_email_conflicts(client):
    await client.post(REGISTER, json=_new_user("dup@firstmed.com"))
    resp = await client.post(REGISTER, json=_new_user("dup@firstmed.com"))
    assert resp.status_code == 409


async def test_register_rejects_short_password(client):
    payload = _new_user("short@firstmed.com")
    payload["password"] = "short"
    resp = await client.post(REGISTER, json=payload)
    assert resp.status_code == 422


async def test_login_and_access_me(client):
    await client.post(REGISTER, json=_new_user("login@firstmed.com"))

    login = await client.post(
        LOGIN,
        data={"username": "login@firstmed.com", "password": "supersecret1"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert login.json()["token_type"] == "bearer"

    me = await client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "login@firstmed.com"


async def test_login_wrong_password_unauthorized(client):
    await client.post(REGISTER, json=_new_user("wrong@firstmed.com"))
    login = await client.post(
        LOGIN,
        data={"username": "wrong@firstmed.com", "password": "incorrect"},
    )
    assert login.status_code == 401


async def test_me_requires_authentication(client):
    resp = await client.get(ME)
    assert resp.status_code == 401


async def test_me_rejects_invalid_token(client):
    resp = await client.get(ME, headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401
