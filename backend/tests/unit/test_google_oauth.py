"""Unit tests for the Google OAuth helper service."""

from __future__ import annotations

import httpx
import jwt
import pytest
from app.core.config import settings
from app.services import google_oauth


def _id_token(claims: dict) -> str:
    return jwt.encode(claims, "unused-secret", algorithm="HS256")


def test_build_authorization_url(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "cid.apps.googleusercontent.com")
    url = google_oauth.build_authorization_url("state-123")
    assert url.startswith(google_oauth.AUTH_URI)
    assert "client_id=cid.apps.googleusercontent.com" in url
    assert "state=state-123" in url
    assert "access_type=offline" in url
    assert "gmail.readonly" in url


def test_state_round_trip():
    state = google_oauth.make_state()
    assert google_oauth.verify_state(state) is True


def test_verify_state_rejects_garbage():
    assert google_oauth.verify_state("not-a-jwt") is False


def test_decode_id_token():
    token = _id_token({"sub": "123", "email": "a@b.com", "name": "A B", "email_verified": True})
    profile = google_oauth.decode_id_token(token)
    assert profile.sub == "123"
    assert profile.email == "a@b.com"
    assert profile.name == "A B"
    assert profile.email_verified is True


def test_decode_id_token_missing_claims():
    token = _id_token({"sub": "123"})  # no email
    with pytest.raises(google_oauth.GoogleOAuthError):
        google_oauth.decode_id_token(token)


async def test_exchange_code():
    def handler(request: httpx.Request) -> httpx.Response:
        assert b"grant_type=authorization_code" in request.content
        return httpx.Response(
            200,
            json={
                "access_token": "at",
                "expires_in": 3600,
                "scope": "openid email",
                "refresh_token": "rt",
                "id_token": "idt",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tokens = await google_oauth.exchange_code("code-123", client=client)
    await client.aclose()

    assert tokens.access_token == "at"
    assert tokens.refresh_token == "rt"
    assert tokens.expires_in == 3600
    assert tokens.id_token == "idt"


async def test_post_token_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="invalid_grant")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(google_oauth.GoogleOAuthError):
        await google_oauth.refresh_access_token("rt", client=client)
    await client.aclose()
