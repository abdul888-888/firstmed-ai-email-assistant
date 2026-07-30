"""Tests for the Gmail service and API (read access to the shared inbox)."""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
from app.core import crypto
from app.models.google_credential import GoogleCredential
from app.models.user import User
from app.repositories.google_credential import GoogleCredentialRepository
from app.services.gmail_service import GmailApiError, GmailNotConnectedError, GmailService


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


async def test_get_message_skips_full_fetch_for_noise_labels(db_session):
    # A promotional email — the account's own Gmail labels already say so.
    # get_message must return without ever making the expensive full-format
    # request (this is the "metadata first" optimization).
    user = await _user_with_credential(db_session)
    calls = {"metadata": 0, "full": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        fmt = request.url.params.get("format")
        assert fmt == "metadata", "must never reach a full-format request for noise mail"
        calls["metadata"] += 1
        return httpx.Response(
            200,
            json={
                "id": "m1",
                "threadId": "t1",
                "snippet": "50% off your next visit!",
                "labelIds": ["INBOX", "CATEGORY_PROMOTIONS"],
                "payload": {"headers": [{"name": "Subject", "value": "Big Sale"}]},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    msg = await GmailService(db_session, client=client).get_message(user, "m1")
    await client.aclose()

    assert calls == {"metadata": 1, "full": 0}
    assert msg["is_noise"] is True
    assert msg["body"] == ""
    assert msg["subject"] == "Big Sale"


async def test_get_message_metadata_requests_specific_headers(db_session):
    user = await _user_with_credential(db_session)
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("format") == "metadata":
            captured["metadataHeaders"] = request.url.params.get_list("metadataHeaders")
            return httpx.Response(
                200,
                json={
                    "id": "m1",
                    "threadId": "t1",
                    "snippet": "s",
                    "labelIds": ["INBOX"],
                    "payload": {"headers": []},
                },
            )
        return httpx.Response(200, json={"id": "m1", "threadId": "t1", "payload": {"headers": []}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await GmailService(db_session, client=client).get_message(user, "m1")
    await client.aclose()

    assert set(captured["metadataHeaders"]) == {"Subject", "From", "To", "Date", "Message-ID"}


async def test_get_message_extracts_full_body(db_session):
    import base64

    user = await _user_with_credential(db_session)
    plain = base64.urlsafe_b64encode(b"Full body text of the email.").decode().rstrip("=")
    html = base64.urlsafe_b64encode(b"<p>ignored html</p>").decode().rstrip("=")
    calls = {"metadata": 0, "full": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        fmt = request.url.params.get("format")
        if fmt == "metadata":
            calls["metadata"] += 1
            return httpx.Response(
                200,
                json={
                    "id": "m1",
                    "threadId": "t1",
                    "snippet": "Full body text",
                    "labelIds": ["INBOX", "UNREAD"],
                    "payload": {"headers": [{"name": "Subject", "value": "Appointment"}]},
                },
            )
        assert fmt == "full"
        calls["full"] += 1
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

    # Metadata fetched first (cheap), then the full MIME payload for the body.
    assert calls == {"metadata": 1, "full": 1}
    # Prefers the text/plain part over text/html.
    assert msg["body"] == "Full body text of the email."
    assert msg["subject"] == "Appointment"
    assert msg["is_noise"] is False


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


# --- retry/backoff on 429/5xx -----------------------------------------------


async def test_retries_on_429_then_succeeds(db_session, monkeypatch):
    from app.services import gmail_service

    monkeypatch.setattr(gmail_service, "_BASE_BACKOFF_SECONDS", 0.001)
    monkeypatch.setattr(gmail_service, "_MAX_BACKOFF_SECONDS", 0.001)
    user = await _user_with_credential(db_session)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, json={"messages": [], "resultSizeEstimate": 0})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    data = await GmailService(db_session, client=client).list_messages(user)
    await client.aclose()

    assert calls["n"] == 3
    assert data["result_size_estimate"] == 0


async def test_retries_honor_retry_after_header(db_session, monkeypatch):
    from app.services import gmail_service

    monkeypatch.setattr(gmail_service, "_MAX_BACKOFF_SECONDS", 10.0)
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(gmail_service.asyncio, "sleep", fake_sleep)
    user = await _user_with_credential(db_session)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(429, text="slow down", headers={"Retry-After": "7"})
        return httpx.Response(200, json={"messages": [], "resultSizeEstimate": 0})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await GmailService(db_session, client=client).list_messages(user)
    await client.aclose()

    assert sleeps == [7.0]  # Retry-After honored exactly, no jitter applied to it


async def test_exhausts_retries_and_raises(db_session, monkeypatch):
    from app.services import gmail_service

    monkeypatch.setattr(gmail_service, "_BASE_BACKOFF_SECONDS", 0.001)
    monkeypatch.setattr(gmail_service, "_MAX_BACKOFF_SECONDS", 0.001)
    monkeypatch.setattr(gmail_service, "_MAX_RETRIES", 2)
    user = await _user_with_credential(db_session)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="down for maintenance")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(GmailApiError) as exc_info:
        await GmailService(db_session, client=client).list_messages(user)
    await client.aclose()

    assert calls["n"] == 3  # initial attempt + 2 retries
    assert exc_info.value.status_code == 503


async def test_does_not_retry_permanent_client_errors(db_session):
    user = await _user_with_credential(db_session)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, text="bad request")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(GmailApiError):
        await GmailService(db_session, client=client).list_messages(user)
    await client.aclose()

    assert calls["n"] == 1  # no retry for a permanent 4xx


# --- history-based incremental sync ------------------------------------------


async def test_get_profile_returns_history_id(db_session):
    user = await _user_with_credential(db_session)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/users/me/profile")
        return httpx.Response(
            200, json={"emailAddress": "clinic@firstmed.com", "historyId": "1000"}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    profile = await GmailService(db_session, client=client).get_profile(user)
    await client.aclose()

    assert profile == {"email_address": "clinic@firstmed.com", "history_id": "1000"}


async def test_get_history_collects_added_messages_and_paginates(db_session):
    user = await _user_with_credential(db_session)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert request.url.params.get("startHistoryId") == "1000"
        if calls["n"] == 1:
            assert "pageToken" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "history": [
                        {"messagesAdded": [{"message": {"id": "m1", "threadId": "t1"}}]}
                    ],
                    "nextPageToken": "page-2",
                    "historyId": "1001",
                },
            )
        assert request.url.params.get("pageToken") == "page-2"
        return httpx.Response(
            200,
            json={
                "history": [
                    {"messagesAdded": [{"message": {"id": "m2", "threadId": "t2"}}]}
                ],
                "historyId": "1005",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await GmailService(db_session, client=client).get_history(user, "1000")
    await client.aclose()

    assert calls["n"] == 2
    assert result["expired"] is False
    assert [m["id"] for m in result["messages"]] == ["m1", "m2"]
    assert result["history_id"] == "1005"  # the LATEST page's historyId


async def test_get_history_deduplicates_repeated_message_ids(db_session):
    user = await _user_with_credential(db_session)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "history": [
                    {"messagesAdded": [{"message": {"id": "m1", "threadId": "t1"}}]},
                    {"messagesAdded": [{"message": {"id": "m1", "threadId": "t1"}}]},
                ],
                "historyId": "1001",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await GmailService(db_session, client=client).get_history(user, "1000")
    await client.aclose()

    assert [m["id"] for m in result["messages"]] == ["m1"]


async def test_get_history_reports_expired_on_404(db_session):
    user = await _user_with_credential(db_session)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="startHistoryId too old")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await GmailService(db_session, client=client).get_history(user, "1")
    await client.aclose()

    assert result == {"messages": [], "history_id": None, "expired": True}


async def test_list_new_messages_bootstraps_history_on_first_pull(db_session):
    # No stored history_id yet — must fall back to the bounded search AND
    # bootstrap a cursor for next time via get_profile.
    user = await _user_with_credential(db_session)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages"):
            assert request.url.params.get("q") == "in:inbox test"
            return httpx.Response(
                200,
                json={
                    "messages": [{"id": "m1", "threadId": "t1"}],
                    "resultSizeEstimate": 1,
                },
            )
        assert request.url.path.endswith("/profile")
        return httpx.Response(200, json={"emailAddress": "x", "historyId": "5000"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await GmailService(db_session, client=client).list_new_messages(
        user, max_results=10, query="in:inbox test"
    )
    await client.aclose()

    assert result["synced_via"] == "full_list"
    assert result["messages"] == [{"id": "m1", "thread_id": "t1"}]

    cred = await GoogleCredentialRepository(db_session).get_by_user_id(user.id)
    assert cred.history_id == "5000"  # bootstrapped for the next pull


async def test_list_new_messages_uses_history_when_cursor_present(db_session):
    user = await _user_with_credential(db_session)
    cred = await GoogleCredentialRepository(db_session).get_by_user_id(user.id)
    await GoogleCredentialRepository(db_session).update_history_id(cred, history_id="1000")
    calls = {"messages_list": 0, "history": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/history"):
            calls["history"] += 1
            assert request.url.params.get("startHistoryId") == "1000"
            return httpx.Response(
                200,
                json={
                    "history": [
                        {"messagesAdded": [{"message": {"id": "new-1", "threadId": "t1"}}]}
                    ],
                    "historyId": "1002",
                },
            )
        calls["messages_list"] += 1  # must NOT be called on the history path
        return httpx.Response(200, json={"messages": [], "resultSizeEstimate": 0})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await GmailService(db_session, client=client).list_new_messages(user)
    await client.aclose()

    assert calls == {"messages_list": 0, "history": 1}
    assert result["synced_via"] == "history"
    assert result["messages"] == [{"id": "new-1", "thread_id": "t1"}]

    refreshed = await GoogleCredentialRepository(db_session).get_by_user_id(user.id)
    assert refreshed.history_id == "1002"  # cursor advanced


async def test_list_new_messages_falls_back_when_history_expired(db_session):
    user = await _user_with_credential(db_session)
    cred = await GoogleCredentialRepository(db_session).get_by_user_id(user.id)
    await GoogleCredentialRepository(db_session).update_history_id(cred, history_id="1")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/history"):
            return httpx.Response(404, text="too old")
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                200,
                json={"messages": [{"id": "m1", "threadId": "t1"}], "resultSizeEstimate": 1},
            )
        return httpx.Response(200, json={"emailAddress": "x", "historyId": "9999"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await GmailService(db_session, client=client).list_new_messages(user)
    await client.aclose()

    assert result["synced_via"] == "full_list"
    assert result["messages"] == [{"id": "m1", "thread_id": "t1"}]

    refreshed = await GoogleCredentialRepository(db_session).get_by_user_id(user.id)
    assert refreshed.history_id == "9999"  # re-bootstrapped after expiry


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
