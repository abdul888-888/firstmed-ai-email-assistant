"""API tests for the Phase 6 workflow trigger (AI + Gmail mocked)."""

from __future__ import annotations

import pytest
from app.core.config import settings
from pydantic import SecretStr

WF = "/api/v1/workflows/gmail/msg-1"


@pytest.fixture
def ai_configured(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr("test-key"))


async def _auth_token(client, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "W", "role": "front_office"},
    )
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login.json()["access_token"]


def _mock_pipeline(monkeypatch, *, intent="prescription_refill", department="nurse"):
    """Mock Gmail fetch + triage + draft; track whether Gmail was written to."""
    calls = {"create_draft": 0}

    async def fake_get_message(self, user, message_id):
        return {
            "id": message_id,
            "thread_id": "t1",
            "message_id_header": "<orig@mail.gmail.com>",
            "snippet": "snippet",
            "body": "Full patient body.",
            "subject": "Refill",
            "from": "patient@example.com",
        }

    async def fake_classify(self, subject, body):
        return {
            "intent": intent,
            "urgency": "normal",
            "department": department,
            "summary": "Patient request.",
            "requires_human_review": True,
            "confidence": 0.9,
        }

    async def fake_generate(self, subject, body, **kwargs):
        return {
            "draft": "Draft reply. The FirstMed Team",
            "model": "claude-haiku-4-5",
            "citations": [
                {"document_id": "d1", "source": "notion", "title": "Refill SOP", "url": None}
            ],
            "requires_human_review": True,
        }

    async def fake_create_draft(self, user, **kwargs):
        calls["create_draft"] += 1
        return {"draft_id": "draft-1", "message_id": "m9", "thread_id": "t1"}

    monkeypatch.setattr("app.services.gmail_service.GmailService.get_message", fake_get_message)
    monkeypatch.setattr("app.services.gmail_service.GmailService.create_draft", fake_create_draft)
    monkeypatch.setattr("app.services.triage_service.TriageService.classify", fake_classify)
    monkeypatch.setattr("app.services.draft_service.DraftService.generate", fake_generate)
    return calls


async def test_workflow_status(client):
    resp = await client.get("/api/v1/workflows/status")
    assert resp.status_code == 200
    assert resp.json() == {"module": "workflows", "implemented": True, "phase": 6}


async def test_workflow_requires_auth(client):
    resp = await client.post(WF)
    assert resp.status_code == 401


async def test_workflow_not_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr(""))
    token = await _auth_token(client, "wf-nc@firstmed.com")
    resp = await client.post(WF, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 503


async def test_workflow_requires_gmail_connection(client, ai_configured):
    token = await _auth_token(client, "wf-nolink@firstmed.com")
    resp = await client.post(WF, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 409


async def test_workflow_creates_pending_review_without_gmail_write(
    client, ai_configured, monkeypatch
):
    calls = _mock_pipeline(monkeypatch)
    token = await _auth_token(client, "wf-ok@firstmed.com")
    resp = await client.post(WF, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["classification"] == "ADMIN_DIRECT_REPLY"  # refill/nurse/normal/0.9
    assert body["intent"] == "prescription_refill"
    assert body["confidence"] == 0.9
    assert body["draft_body"].startswith("Draft reply")
    assert body["citations"][0]["title"] == "Refill SOP"
    assert body["gmail_draft_id"] is None
    # The pipeline must NOT touch Gmail before approval.
    assert calls["create_draft"] == 0


async def test_workflow_clinical_email_is_escalated(client, ai_configured, monkeypatch):
    _mock_pipeline(monkeypatch, intent="medical_question", department="nurse")
    token = await _auth_token(client, "wf-clin@firstmed.com")
    resp = await client.post(WF, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["classification"] == "NEEDS_PHYSICIAN_REVIEW"
