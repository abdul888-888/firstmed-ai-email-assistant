"""API tests for the Google OAuth staff-SSO flow."""

from __future__ import annotations

import pytest
from app.core import crypto
from app.core.config import settings
from app.repositories.google_credential import GoogleCredentialRepository
from app.repositories.user import UserRepository
from app.services import google_oauth
from pydantic import SecretStr

LOGIN_URL = "/api/v1/auth/google/login"
CALLBACK = "/api/v1/auth/google/callback"


@pytest.fixture
def google_configured(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "cid")
    monkeypatch.setattr(settings, "google_client_secret", SecretStr("secret"))


async def test_google_login_requires_config(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "google_client_secret", SecretStr(""))
    resp = await client.get(LOGIN_URL)
    assert resp.status_code == 503


async def test_google_login_returns_url(client, google_configured):
    resp = await client.get(LOGIN_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["authorization_url"].startswith(google_oauth.AUTH_URI)
    assert google_oauth.verify_state(body["state"]) is True


async def test_google_callback_invalid_state(client, google_configured):
    resp = await client.get(f"{CALLBACK}?code=abc&state=bogus", follow_redirects=False)
    assert resp.status_code == 400


async def test_google_callback_user_denied(client, google_configured):
    resp = await client.get(f"{CALLBACK}?error=access_denied", follow_redirects=False)
    assert resp.status_code == 303
    assert "error=access_denied" in resp.headers["location"]


async def test_google_callback_provisions_user_and_stores_credential(
    client, db_session, google_configured, monkeypatch
):
    async def fake_exchange(code, *, client=None):
        return google_oauth.GoogleTokens(
            access_token="access-abc",
            expires_in=3600,
            scope="openid email https://www.googleapis.com/auth/gmail.readonly",
            refresh_token="refresh-xyz",
            id_token="idt",
        )

    def fake_decode(id_token):
        return google_oauth.GoogleProfile(
            sub="google-sub-1",
            email="doctor@firstmed.com",
            name="Dr Who",
            email_verified=True,
        )

    monkeypatch.setattr(google_oauth, "exchange_code", fake_exchange)
    monkeypatch.setattr(google_oauth, "decode_id_token", fake_decode)

    state = google_oauth.make_state()
    resp = await client.get(f"{CALLBACK}?code=auth-code&state={state}", follow_redirects=False)

    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location.startswith(settings.frontend_base_url)
    assert "access_token=" in location

    # User was provisioned without a local password.
    user = await UserRepository(db_session).get_by_email("doctor@firstmed.com")
    assert user is not None
    assert user.hashed_password is None
    assert user.full_name == "Dr Who"

    # Credential stored, tokens encrypted at rest.
    cred = await GoogleCredentialRepository(db_session).get_by_user_id(user.id)
    assert cred is not None
    assert cred.google_sub == "google-sub-1"
    assert cred.access_token_enc != "access-abc"
    assert crypto.decrypt(cred.access_token_enc) == "access-abc"
    assert crypto.decrypt(cred.refresh_token_enc) == "refresh-xyz"
    assert "gmail.readonly" in cred.scopes
