"""API tests for the Phase 8 review-queue slice (AI + Gmail mocked)."""

from __future__ import annotations

import pytest
from app.core.config import settings


@pytest.fixture
def ai_configured(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")


async def _auth_token(client, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "R", "role": "front_office"},
    )
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login.json()["access_token"]


def _mock_pipeline(monkeypatch):
    calls = {"create_draft": 0, "create_draft_kwargs": None}

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
            "intent": "prescription_refill",
            "urgency": "normal",
            "department": "nurse",
            "summary": "Refill request.",
            "requires_human_review": True,
            "confidence": 0.9,
        }

    async def fake_generate(self, subject, body, **kwargs):
        return {
            "draft": "Draft reply. The FirstMed Team",
            "model": "claude-haiku-4-5",
            "citations": [],
            "requires_human_review": True,
        }

    async def fake_create_draft(self, user, **kwargs):
        calls["create_draft"] += 1
        calls["create_draft_kwargs"] = kwargs
        return {"draft_id": "draft-1", "message_id": "m9", "thread_id": "t1"}

    async def fake_send_draft(self, user, draft_id):
        calls["send_draft"] = draft_id
        return {"message_id": "sent-99", "thread_id": "t1", "label_ids": ["SENT"]}

    monkeypatch.setattr("app.services.gmail_service.GmailService.get_message", fake_get_message)
    monkeypatch.setattr("app.services.gmail_service.GmailService.create_draft", fake_create_draft)
    monkeypatch.setattr("app.services.gmail_service.GmailService.send_draft", fake_send_draft)
    monkeypatch.setattr("app.services.triage_service.TriageService.classify", fake_classify)
    monkeypatch.setattr("app.services.draft_service.DraftService.generate", fake_generate)
    return calls


async def _create_review(client, token) -> str:
    resp = await client.post(
        "/api/v1/workflows/gmail/msg-1", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    return resp.json()["id"]


async def test_pending_requires_auth(client):
    resp = await client.get("/api/v1/reviews/pending")
    assert resp.status_code == 401


async def test_pending_empty(client):
    token = await _auth_token(client, "rv-empty@firstmed.com")
    resp = await client.get("/api/v1/reviews/pending", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"reviews": [], "count": 0}


async def test_pending_lists_created_review(client, ai_configured, monkeypatch):
    _mock_pipeline(monkeypatch)
    token = await _auth_token(client, "rv-list@firstmed.com")
    review_id = await _create_review(client, token)

    resp = await client.get("/api/v1/reviews/pending", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["reviews"][0]["id"] == review_id
    assert body["reviews"][0]["classification"] == "ADMIN_DIRECT_REPLY"


async def test_approve_pushes_threaded_draft_and_flips_status(client, ai_configured, monkeypatch):
    calls = _mock_pipeline(monkeypatch)
    token = await _auth_token(client, "rv-approve@firstmed.com")
    review_id = await _create_review(client, token)
    assert calls["create_draft"] == 0  # not yet — deferred

    resp = await client.post(
        f"/api/v1/reviews/{review_id}/approve", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["gmail_draft_id"] == "draft-1"
    assert body["reviewed_at"] is not None
    # Draft pushed exactly once, threaded, addressed to the sender.
    assert calls["create_draft"] == 1
    kw = calls["create_draft_kwargs"]
    assert kw["to"] == "patient@example.com"
    assert kw["subject"] == "Re: Refill"
    assert kw["thread_id"] == "t1"
    assert kw["in_reply_to"] == "<orig@mail.gmail.com>"

    # No longer pending.
    pending = await client.get(
        "/api/v1/reviews/pending", headers={"Authorization": f"Bearer {token}"}
    )
    assert pending.json()["count"] == 0


async def test_approve_twice_conflicts(client, ai_configured, monkeypatch):
    _mock_pipeline(monkeypatch)
    token = await _auth_token(client, "rv-twice@firstmed.com")
    review_id = await _create_review(client, token)
    h = {"Authorization": f"Bearer {token}"}
    assert (await client.post(f"/api/v1/reviews/{review_id}/approve", headers=h)).status_code == 200
    resp = await client.post(f"/api/v1/reviews/{review_id}/approve", headers=h)
    assert resp.status_code == 409


async def test_approve_unknown_id_404(client):
    token = await _auth_token(client, "rv-404@firstmed.com")
    resp = await client.post(
        "/api/v1/reviews/00000000-0000-0000-0000-000000000000/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_cannot_access_another_users_review(client, ai_configured, monkeypatch):
    _mock_pipeline(monkeypatch)
    owner = await _auth_token(client, "rv-owner@firstmed.com")
    review_id = await _create_review(client, owner)

    other = await _auth_token(client, "rv-other@firstmed.com")
    resp = await client.get(
        f"/api/v1/reviews/{review_id}", headers={"Authorization": f"Bearer {other}"}
    )
    assert resp.status_code == 404


async def test_edit_updates_draft_body(client, ai_configured, monkeypatch):
    _mock_pipeline(monkeypatch)
    token = await _auth_token(client, "rv-edit@firstmed.com")
    h = {"Authorization": f"Bearer {token}"}
    review_id = await _create_review(client, token)

    resp = await client.patch(
        f"/api/v1/reviews/{review_id}", json={"draft_body": "Edited reply text."}, headers=h
    )
    assert resp.status_code == 200
    assert resp.json()["draft_body"] == "Edited reply text."

    # The edit persists and is what gets pushed on approve.
    calls = _mock_pipeline(monkeypatch)  # reset call tracking
    await client.post(f"/api/v1/reviews/{review_id}/approve", headers=h)
    assert calls["create_draft_kwargs"]["body"] == "Edited reply text."


async def test_edit_rejected_when_not_pending(client, ai_configured, monkeypatch):
    _mock_pipeline(monkeypatch)
    token = await _auth_token(client, "rv-editlock@firstmed.com")
    h = {"Authorization": f"Bearer {token}"}
    review_id = await _create_review(client, token)
    await client.post(f"/api/v1/reviews/{review_id}/approve", headers=h)

    resp = await client.patch(
        f"/api/v1/reviews/{review_id}", json={"draft_body": "too late"}, headers=h
    )
    assert resp.status_code == 409


async def test_reject_sets_status_and_note(client, ai_configured, monkeypatch):
    calls = _mock_pipeline(monkeypatch)
    token = await _auth_token(client, "rv-reject@firstmed.com")
    h = {"Authorization": f"Bearer {token}"}
    review_id = await _create_review(client, token)

    resp = await client.post(
        f"/api/v1/reviews/{review_id}/reject",
        json={"reason": "Wrong department — route to billing."},
        headers=h,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["review_note"] == "Wrong department — route to billing."
    assert calls["create_draft"] == 0  # reject never touches Gmail
    # Gone from pending; visible under rejected.
    assert (await client.get("/api/v1/reviews/pending", headers=h)).json()["count"] == 0
    rej = await client.get("/api/v1/reviews?status=rejected", headers=h)
    assert rej.json()["count"] == 1


async def test_send_flow(client, ai_configured, monkeypatch):
    calls = _mock_pipeline(monkeypatch)
    token = await _auth_token(client, "rv-send@firstmed.com")
    h = {"Authorization": f"Bearer {token}"}
    review_id = await _create_review(client, token)

    # Cannot send before approve.
    assert (await client.post(f"/api/v1/reviews/{review_id}/send", headers=h)).status_code == 409

    await client.post(f"/api/v1/reviews/{review_id}/approve", headers=h)
    resp = await client.post(f"/api/v1/reviews/{review_id}/send", headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "sent"
    assert body["sent_message_id"] == "sent-99"
    assert calls["send_draft"] == "draft-1"  # sent the approved draft
    # Now under 'sent', not 'approved'.
    assert (await client.get("/api/v1/reviews?status=approved", headers=h)).json()["count"] == 0
    assert (await client.get("/api/v1/reviews?status=sent", headers=h)).json()["count"] == 1
