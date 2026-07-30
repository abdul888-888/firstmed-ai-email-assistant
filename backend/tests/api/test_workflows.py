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


def _mock_pipeline(
    monkeypatch,
    *,
    intent="prescription_refill",
    department="nurse",
    body="Full patient body.",
    grounded=True,
):
    """Mock Gmail fetch + triage + draft.

    Tracks whether Gmail was written to (``create_draft``) and whether draft
    generation was even reached (``generate``) so tests can assert that excluded
    emails never reach the LLM. ``grounded=False`` simulates a knowledge-base miss.
    """
    calls = {"create_draft": 0, "generate": 0}

    async def fake_get_message(self, user, message_id):
        return {
            "id": message_id,
            "thread_id": "t1",
            "message_id_header": "<orig@mail.gmail.com>",
            "snippet": "snippet",
            "body": body,
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
        calls["generate"] += 1
        if kwargs.get("abstain_if_ungrounded") and not grounded:
            return {
                "draft": "",
                "model": "claude-haiku-4-5",
                "citations": [],
                "grounded": False,
                "requires_human_review": True,
            }
        return {
            "draft": "Draft reply. The FirstMed Team",
            "model": "claude-haiku-4-5",
            "citations": [
                {"document_id": "d1", "source": "notion", "title": "Refill SOP", "url": None}
            ],
            "grounded": True,
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
    calls = _mock_pipeline(monkeypatch, intent="medical_question", department="nurse")
    token = await _auth_token(client, "wf-clin@firstmed.com")
    resp = await client.post(WF, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["classification"] == "NEEDS_PHYSICIAN_REVIEW"
    # Clinical email must NOT be AI-drafted: no generation, empty draft.
    assert calls["generate"] == 0
    assert body["draft_body"] == ""
    assert body["status"] == "awaiting_specialist_input"


async def test_workflow_appointment_is_routed_never_drafted(client, ai_configured, monkeypatch):
    # THE reported bug: appointment emails must never get an AI draft.
    calls = _mock_pipeline(monkeypatch, intent="appointment", department="front_office")
    token = await _auth_token(client, "wf-appt@firstmed.com")
    resp = await client.post(WF, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["classification"] == "ROUTE_TO_STAFF"
    assert body["status"] == "needs_manual_handling"
    assert body["draft_body"] == ""
    assert calls["generate"] == 0  # draft generation never even reached
    assert calls["create_draft"] == 0


async def test_workflow_emergency_keyword_escalates(client, ai_configured, monkeypatch):
    # Even if triage mislabels the intent, emergency language forces escalation.
    calls = _mock_pipeline(
        monkeypatch,
        intent="billing_insurance",
        department="front_office",
        body="I have severe chest pain and trouble breathing.",
    )
    token = await _auth_token(client, "wf-911@firstmed.com")
    resp = await client.post(WF, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["classification"] == "NEEDS_PHYSICIAN_REVIEW"
    assert calls["generate"] == 0
    assert body["draft_body"] == ""


async def test_workflow_lab_results_never_drafted_even_if_mistriaged(client, ai_configured, monkeypatch):
    # The LLM mislabels a results request as routine "other" — the deterministic
    # lab-results gate must still block drafting and route to a clinician.
    calls = _mock_pipeline(
        monkeypatch,
        intent="other",
        department="front_office",
        body="Hi, are my blood test results ready yet?",
    )
    token = await _auth_token(client, "wf-lab-results@firstmed.com")
    resp = await client.post(WF, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["classification"] == "NEEDS_PHYSICIAN_REVIEW"
    assert body["department"] == "laboratory"
    assert body["draft_body"] == ""
    assert calls["generate"] == 0


async def test_workflow_lab_preparation_question_gets_drafted(client, ai_configured, monkeypatch):
    # Preparation questions ARE allowed — this must reach draft generation and
    # be tagged to the laboratory department for staff visibility.
    calls = _mock_pipeline(
        monkeypatch,
        intent="other",
        department="front_office",
        body="Do I need to fast before my blood test tomorrow?",
    )
    token = await _auth_token(client, "wf-lab-prep@firstmed.com")
    resp = await client.post(WF, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["classification"] == "ADMIN_DIRECT_REPLY"
    assert body["department"] == "laboratory"
    assert body["draft_body"].startswith("Draft reply")
    assert calls["generate"] == 1


async def test_workflow_gastro_procedure_booking_routed_never_drafted(client, ai_configured, monkeypatch):
    calls = _mock_pipeline(
        monkeypatch,
        intent="appointment",
        department="front_office",
        body="I'd like to schedule a colonoscopy next month.",
    )
    token = await _auth_token(client, "wf-gastro@firstmed.com")
    resp = await client.post(WF, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["classification"] == "ROUTE_TO_STAFF"
    assert body["department"] == "gastroenterology"
    assert body["draft_body"] == ""
    assert calls["generate"] == 0


async def test_workflow_physio_request_routed_never_drafted(client, ai_configured, monkeypatch):
    # Physio is booked directly by the physiotherapy team, never AI-drafted,
    # regardless of whether a referral was already given.
    calls = _mock_pipeline(
        monkeypatch,
        intent="appointment",
        department="front_office",
        body="I'd like to book physio for my shoulder.",
    )
    token = await _auth_token(client, "wf-physio@firstmed.com")
    resp = await client.post(WF, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["classification"] == "ROUTE_TO_STAFF"
    assert body["department"] == "physiotherapy"
    assert body["draft_body"] == ""
    assert calls["generate"] == 0


async def test_workflow_duplicate_message_conflicts(client, ai_configured, monkeypatch):
    # A retried/racing call to run_gmail for the same message must not create a
    # second review row — the DB unique constraint backstops the read-then-write
    # dedup and surfaces as a 409, not a duplicate card or a 500.
    _mock_pipeline(monkeypatch)
    token = await _auth_token(client, "wf-dup@firstmed.com")
    headers = {"Authorization": f"Bearer {token}"}

    first = await client.post(WF, headers=headers)
    assert first.status_code == 200

    second = await client.post(WF, headers=headers)
    assert second.status_code == 409


# --- Celery async pull: /pull-async + /pull-async/{task_id} -----------------
# No real broker/worker is contacted in these tests — pull_gmail_task.delay and
# AsyncResult are monkeypatched, since enqueue/status-check is all the HTTP
# layer does (the task's own logic is covered in tests/unit/test_workflow_tasks.py).


async def test_pull_async_requires_auth(client):
    resp = await client.post("/api/v1/workflows/pull-async")
    assert resp.status_code == 401


async def test_pull_async_not_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr(""))
    token = await _auth_token(client, "wf-async-nc@firstmed.com")
    resp = await client.post(
        "/api/v1/workflows/pull-async", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 503


async def test_pull_async_enqueues_and_returns_task_id(client, ai_configured, monkeypatch):
    class FakeAsyncResult:
        id = "fake-task-id-123"

    def fake_delay(user_id, max_results, query):
        return FakeAsyncResult()

    monkeypatch.setattr("app.api.workflows.pull_gmail_task.delay", fake_delay)
    token = await _auth_token(client, "wf-async-ok@firstmed.com")
    resp = await client.post(
        "/api/v1/workflows/pull-async", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 202
    assert resp.json() == {"task_id": "fake-task-id-123", "status": "queued"}


async def test_pull_async_status_pending(client, ai_configured, monkeypatch):
    class FakeResult:
        def __init__(self, task_id, app=None):
            self.state = "PENDING"
            self.result = None

    monkeypatch.setattr("app.api.workflows.AsyncResult", FakeResult)
    token = await _auth_token(client, "wf-async-status-pending@firstmed.com")
    resp = await client.get(
        "/api/v1/workflows/pull-async/some-task-id",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"task_id": "some-task-id", "state": "PENDING"}


async def test_pull_async_status_success(client, ai_configured, monkeypatch):
    class FakeResult:
        def __init__(self, task_id, app=None):
            self.state = "SUCCESS"
            self.result = {"created": 2, "skipped": 1, "failed": 0, "scanned": 3}

    monkeypatch.setattr("app.api.workflows.AsyncResult", FakeResult)
    token = await _auth_token(client, "wf-async-status-success@firstmed.com")
    resp = await client.get(
        "/api/v1/workflows/pull-async/some-task-id",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "SUCCESS"
    assert body["result"] == {"created": 2, "skipped": 1, "failed": 0, "scanned": 3}


async def test_pull_async_status_failure(client, ai_configured, monkeypatch):
    class FakeResult:
        def __init__(self, task_id, app=None):
            self.state = "FAILURE"
            self.result = RuntimeError("Gmail API is down")

    monkeypatch.setattr("app.api.workflows.AsyncResult", FakeResult)
    token = await _auth_token(client, "wf-async-status-failure@firstmed.com")
    resp = await client.get(
        "/api/v1/workflows/pull-async/some-task-id",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "FAILURE"
    assert "Gmail API is down" in body["error"]


async def test_workflow_abstains_on_knowledge_gap(client, ai_configured, monkeypatch):
    # Admin email but no KB grounding → abstain, route to manual handling.
    calls = _mock_pipeline(
        monkeypatch, intent="billing_insurance", department="front_office", grounded=False
    )
    token = await _auth_token(client, "wf-gap@firstmed.com")
    resp = await client.post(WF, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "needs_manual_handling"
    assert body["draft_body"] == ""
    assert calls["generate"] == 1  # generation was attempted but abstained
    assert calls["create_draft"] == 0
