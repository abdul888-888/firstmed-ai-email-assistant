"""Tests for the Gmail service and API (read access to the shared inbox)."""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
from app.core import crypto
from app.models.google_credential import GoogleCredential
from app.models.user import User
from app.repositories.google_credential import GoogleCredentialRepository
from app.services.gmail_service import GmailNotConnectedError, GmailService


async def _user(db_session, email: str = "doc@firstmed.com") -> User:
    user = User(email=email, full_name="Doc")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _user_with_credential(db_session, *, expired: bool = False) -> User:
    user = await _user(db_session)
    delta = dt.timedelta(seconds=-10 if expired else 3600)
    cred = GoogleCredential(
        user_id=user.id,
        google_sub="sub",
        google_email=user.email,
        access_token_enc=crypto.encrypt("old-access"),
        refresh_token_enc=crypto.encrypt("refresh-token"),
        token_expiry=dt.datetime.now(dt.UTC) + delta,
        scopes="openid https://www.googleapis.com/auth/gmail.readonly",
    )
    db_session.add(cred)
    await db_session.commit()
    return user


# --- service layer --------------------------------------------------------


async def test_list_messages(db_session):
    user = await _user_with_credential(db_session)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/users/me/messages")
        assert request.headers["authorization"] == "Bearer old-access"
        return httpx.Response(
            200,
            json={
                "messages": [
                    {"id": "m1", "threadId": "t1"},
                    {"id": "m2", "threadId": "t2"},
                ],
                "resultSizeEstimate": 2,
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    data = await GmailService(db_session, client=client).list_messages(user, max_results=10)
    await client.aclose()

    assert data["result_size_estimate"] == 2
    assert data["messages"][0] == {"id": "m1", "thread_id": "t1"}


async def test_get_message_parses_headers(db_session):
    user = await _user_with_credential(db_session)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "m1",
                "threadId": "t1",
                "snippet": "Hello there",
                "labelIds": ["INBOX", "UNREAD"],
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Appointment"},
                        {"name": "From", "value": "patient@example.com"},
                        {"name": "To", "value": "clinic@firstmed.com"},
                    ]
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    msg = await GmailService(db_session, client=client).get_message(user, "m1")
    await client.aclose()

    assert msg["subject"] == "Appointment"
    assert msg["from"] == "patient@example.com"
    assert msg["snippet"] == "Hello there"
    assert msg["label_ids"] == ["INBOX", "UNREAD"]


async def test_get_message_extracts_full_body(db_session):
    import base64

    user = await _user_with_credential(db_session)
    plain = base64.urlsafe_b64encode(b"Full body text of the email.").decode().rstrip("=")
    html = base64.urlsafe_b64encode(b"<p>ignored html</p>").decode().rstrip("=")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("format") == "full"
        return httpx.Response(
            200,
            json={
                "id": "m1",
                "threadId": "t1",
                "snippet": "Full body text",
                "payload": {
                    "mimeType": "multipart/alternative",
                    "headers": [{"name": "Subject", "value": "Appointment"}],
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": plain}},
                        {"mimeType": "text/html", "body": {"data": html}},
                    ],
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    msg = await GmailService(db_session, client=client).get_message(user, "m1")
    await client.aclose()

    # Prefers the text/plain part over text/html.
    assert msg["body"] == "Full body text of the email."
    assert msg["subject"] == "Appointment"


async def test_expired_token_is_refreshed(db_session):
    user = await _user_with_credential(db_session, expired=True)
    calls = {"token": 0, "gmail": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            calls["token"] += 1
            return httpx.Response(
                200, json={"access_token": "fresh-access", "expires_in": 3600, "scope": "openid"}
            )
        calls["gmail"] += 1
        assert request.headers["authorization"] == "Bearer fresh-access"
        return httpx.Response(200, json={"messages": [], "resultSizeEstimate": 0})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await GmailService(db_session, client=client).list_messages(user)
    await client.aclose()

    assert calls == {"token": 1, "gmail": 1}
    # New access token persisted (encrypted).
    cred = await GoogleCredentialRepository(db_session).get_by_user_id(user.id)
    assert crypto.decrypt(cred.access_token_enc) == "fresh-access"


async def test_service_raises_when_not_connected(db_session):
    user = await _user(db_session, email="nolink@firstmed.com")
    with pytest.raises(GmailNotConnectedError):
        await GmailService(db_session).list_messages(user)


async def test_create_draft_posts_encoded_message(db_session):
    import base64

    user = await _user_with_credential(db_session)
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/users/me/drafts")
        captured["body"] = request.read()
        return httpx.Response(
            200,
            json={"id": "draft-1", "message": {"id": "m9", "threadId": "t1"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await GmailService(db_session, client=client).create_draft(
        user,
        to="patient@example.com",
        subject="Re: Appointment",
        body="Thanks for reaching out. The FirstMed Team",
        thread_id="t1",
    )
    await client.aclose()

    assert result == {"draft_id": "draft-1", "message_id": "m9", "thread_id": "t1"}
    import json as _json

    sent = _json.loads(captured["body"])
    assert sent["message"]["threadId"] == "t1"
    raw = base64.urlsafe_b64decode(sent["message"]["raw"]).decode()
    assert "To: patient@example.com" in raw
    assert "Subject: Re: Appointment" in raw
    assert "The FirstMed Team" in raw


async def test_create_draft_sets_threading_headers(db_session):
    import base64

    user = await _user_with_credential(db_session)
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"id": "d1", "message": {"id": "m1", "threadId": "t1"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await GmailService(db_session, client=client).create_draft(
        user,
        to="patient@example.com",
        subject="Re: Refill",
        body="Reply body.",
        thread_id="t1",
        in_reply_to="<orig-msg-id@mail.gmail.com>",
    )
    await client.aclose()

    import json as _json

    raw = base64.urlsafe_b64decode(_json.loads(captured["body"])["message"]["raw"]).decode()
    assert "In-Reply-To: <orig-msg-id@mail.gmail.com>" in raw
    assert "References: <orig-msg-id@mail.gmail.com>" in raw


async def test_list_drafts(db_session):
    user = await _user_with_credential(db_session)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/users/me/drafts")
        return httpx.Response(
            200,
            json={
                "drafts": [{"id": "d1", "message": {"id": "m1", "threadId": "t1"}}],
                "resultSizeEstimate": 1,
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    data = await GmailService(db_session, client=client).list_drafts(user, max_results=5)
    await client.aclose()

    assert data["result_size_estimate"] == 1
    assert data["drafts"][0] == {"id": "d1", "message_id": "m1", "thread_id": "t1"}


# --- API layer ------------------------------------------------------------


async def _auth_token(client, email: str = "g@firstmed.com") -> str:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "supersecret1",
            "full_name": "G",
            "role": "front_office",
        },
    )
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login.json()["access_token"]


async def test_gmail_status_reports_implemented(client):
    resp = await client.get("/api/v1/gmail/status")
    assert resp.status_code == 200
    assert resp.json() == {"module": "gmail", "implemented": True, "phase": 2}


async def test_gmail_connection_not_connected(client):
    token = await _auth_token(client)
    resp = await client.get(
        "/api/v1/gmail/connection", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


async def test_gmail_messages_requires_connection(client):
    token = await _auth_token(client)
    resp = await client.get("/api/v1/gmail/messages", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 409


async def test_gmail_messages_requires_auth(client):
    resp = await client.get("/api/v1/gmail/messages")
    assert resp.status_code == 401


async def test_gmail_drafts_requires_connection(client):
    token = await _auth_token(client, email="drafts1@firstmed.com")
    resp = await client.get(
        "/api/v1/gmail/drafts", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 409


async def test_gmail_drafts_requires_auth(client):
    resp = await client.get("/api/v1/gmail/drafts")
    assert resp.status_code == 401


async def test_gmail_draft_alias_requires_connection(client, monkeypatch):
    from app.core.config import settings
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr("test-key"))
    token = await _auth_token(client, email="alias1@firstmed.com")
    resp = await client.post(
        "/api/v1/gmail/messages/msg-1/draft",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


async def test_gmail_draft_alias_not_configured(client, monkeypatch):
    from app.core.config import settings
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr(""))
    token = await _auth_token(client, email="alias2@firstmed.com")
    resp = await client.post(
        "/api/v1/gmail/messages/msg-1/draft",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503


async def test_gmail_draft_alias_pipeline(client, monkeypatch):
    from app.core.config import settings
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr("test-key"))

    async def fake_get_message(self, user, message_id):
        return {
            "id": message_id,
            "thread_id": "t1",
            "snippet": "snippet proxy",
            "body": "Full body: can I refill my prescription?",
            "subject": "Refill",
            "from": "patient@example.com",
        }

    async def fake_generate(self, subject, body, **kwargs):
        # The full body must reach the drafting stage, not the snippet.
        assert body == "Full body: can I refill my prescription?"
        return {
            "draft": "Thanks for reaching out. The FirstMed Team",
            "model": "claude-haiku-4-5",
            "citations": [],
            "requires_human_review": True,
        }

    captured: dict = {}

    async def fake_create_draft(self, user, *, to, subject, body, thread_id=None, in_reply_to=None):
        captured.update(to=to, subject=subject, thread_id=thread_id)
        return {"draft_id": "draft-1", "message_id": "m9", "thread_id": thread_id or "t1"}

    monkeypatch.setattr("app.services.gmail_service.GmailService.get_message", fake_get_message)
    monkeypatch.setattr("app.services.gmail_service.GmailService.create_draft", fake_create_draft)
    monkeypatch.setattr("app.services.draft_service.DraftService.generate", fake_generate)

    token = await _auth_token(client, email="alias3@firstmed.com")
    resp = await client.post(
        "/api/v1/gmail/messages/msg-123/draft",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["gmail_draft_id"] == "draft-1"
    assert body["source_message_id"] == "msg-123"
    assert body["requires_human_review"] is True
    assert captured == {"to": "patient@example.com", "subject": "Re: Refill", "thread_id": "t1"}
