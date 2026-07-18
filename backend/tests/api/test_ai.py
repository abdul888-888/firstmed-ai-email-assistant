"""API tests for the AI triage + draft endpoints (AI client mocked)."""

from __future__ import annotations

import pytest
from app.core.config import settings
from pydantic import SecretStr
from app.models.document import DocumentSource
from app.repositories.document import DocumentRepository

TRIAGE = "/api/v1/ai/triage"
DRAFT = "/api/v1/ai/draft"


@pytest.fixture
def ai_configured(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr("test-key"))


async def _auth_token(client, email: str = "ai@firstmed.com") -> str:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "supersecret1",
            "full_name": "AI",
            "role": "front_office",
        },
    )
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login.json()["access_token"]


async def test_ai_status(client):
    resp = await client.get("/api/v1/ai/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["module"] == "ai"
    assert body["implemented"] is True
    assert body["model"] == settings.ai_model


async def test_triage_requires_auth(client):
    resp = await client.post(TRIAGE, json={"subject": "x", "body": "y"})
    assert resp.status_code == 401


async def test_triage_not_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr(""))
    token = await _auth_token(client)
    resp = await client.post(
        TRIAGE,
        json={"subject": "Refill", "body": "Please refill"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503


async def test_triage_returns_classification(client, ai_configured, monkeypatch):
    async def fake_structured(self, *, system, user, schema, max_tokens=None):
        return {
            "intent": "prescription_refill",
            "urgency": "normal",
            "department": "nurse",
            "summary": "Patient requests a refill.",
            "requires_human_review": True,
            "confidence": 0.92,
        }

    monkeypatch.setattr("app.ai.client.AIClient.structured", fake_structured)
    token = await _auth_token(client)
    resp = await client.post(
        TRIAGE,
        json={"subject": "Refill", "body": "Please refill my prescription"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "prescription_refill"
    assert body["department"] == "nurse"
    assert body["requires_human_review"] is True


async def test_triage_rejects_empty_body(client, ai_configured):
    token = await _auth_token(client)
    resp = await client.post(
        TRIAGE, json={"subject": "x", "body": ""}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 422


async def test_draft_returns_draft_with_citations(client, db_session, ai_configured, monkeypatch):
    await DocumentRepository(db_session).upsert(
        source=DocumentSource.notion.value,
        source_id="sop1",
        title="Refill SOP",
        content="Refills are handled within 48 hours by a nurse.",
        url="https://notion.so/sop1",
    )

    async def fake_text(self, *, system, user, max_tokens=None, thinking=True):
        return "Thanks for reaching out. The FirstMed Team"

    monkeypatch.setattr("app.ai.client.AIClient.text", fake_text)
    token = await _auth_token(client)
    resp = await client.post(
        DRAFT,
        json={"subject": "Refill", "body": "Can I refill my prescription?", "use_context": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["draft"].startswith("Thanks for reaching out")
    assert body["requires_human_review"] is True
    assert len(body["citations"]) == 1
    assert body["citations"][0]["title"] == "Refill SOP"


async def test_draft_gmail_requires_connection(client, ai_configured):
    # Authenticated user with no linked Google account → 409 before any AI call.
    token = await _auth_token(client)
    resp = await client.post(
        "/api/v1/ai/draft/gmail/msg-123",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


async def test_draft_gmail_push_pipeline(client, ai_configured, monkeypatch):
    async def fake_get_message(self, user, message_id):
        return {
            "id": message_id,
            "thread_id": "t1",
            "snippet": "Can I refill my prescription?",
            "subject": "Refill",
            "from": "patient@example.com",
        }

    async def fake_generate(self, subject, body, **kwargs):
        return {
            "draft": "Thanks for reaching out. The FirstMed Team",
            "model": "claude-haiku-4-5",
            "citations": [],
            "requires_human_review": True,
        }

    captured: dict = {}

    async def fake_create_draft(self, user, *, to, subject, body, thread_id=None, in_reply_to=None):
        captured.update(to=to, subject=subject, body=body, thread_id=thread_id)
        return {"draft_id": "draft-1", "message_id": "m9", "thread_id": thread_id or "t1"}

    monkeypatch.setattr("app.services.gmail_service.GmailService.get_message", fake_get_message)
    monkeypatch.setattr("app.services.gmail_service.GmailService.create_draft", fake_create_draft)
    monkeypatch.setattr("app.services.draft_service.DraftService.generate", fake_generate)

    token = await _auth_token(client)
    resp = await client.post(
        "/api/v1/ai/draft/gmail/msg-123/push",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["gmail_draft_id"] == "draft-1"
    assert body["source_message_id"] == "msg-123"
    assert body["requires_human_review"] is True
    # Reply is addressed to the sender, subject prefixed, kept in-thread.
    assert captured["to"] == "patient@example.com"
    assert captured["subject"] == "Re: Refill"
    assert captured["thread_id"] == "t1"
