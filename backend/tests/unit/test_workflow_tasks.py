"""Unit tests for the Celery Gmail pull tasks (no real broker/worker needed).

``_pull_gmail_async`` / ``_list_connected_user_ids_async`` take an injectable
``session_factory`` so they run against the isolated per-test SQLite DB rather
than the app's real configured database. The Celery-decorated task wrappers
are exercised by calling them directly as functions — Celery resolves ``self``
for ``bind=True`` tasks even when called this way (no dispatch/broker needed),
which is enough to test the asyncio-bridge and retry/no-retry classification
without a live Redis broker or worker process.
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.client import AINotConfiguredError
from app.models.google_credential import GoogleCredential
from app.models.user import User
from app.services.gmail_service import GmailApiError, GmailNotConnectedError
from app.tasks import workflow_tasks


async def _user(db_session, email="celery@firstmed.com") -> User:
    user = User(email=email, full_name="Celery")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _link_google(db_session, user: User) -> None:
    db_session.add(
        GoogleCredential(
            user_id=user.id,
            google_sub="sub-1",
            google_email=user.email,
            access_token_enc="enc-token",
            refresh_token_enc="enc-refresh",
            scopes="gmail.readonly gmail.compose",
        )
    )
    await db_session.commit()


def _mock_pipeline(monkeypatch, *, intent="prescription_refill", department="nurse"):
    async def fake_list_new_messages(self, user, *, max_results=25, query=None):
        return {"messages": [{"id": "m1", "thread_id": "t1"}], "mailbox": "me", "synced_via": "full_list"}

    async def fake_get_message(self, user, message_id):
        return {
            "id": message_id,
            "thread_id": "t1",
            "message_id_header": "<orig@mail.gmail.com>",
            "snippet": "snippet",
            "body": "Full patient body.",
            "subject": "Refill",
            "from": "patient@example.com",
            "is_noise": False,
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
            "citations": [],
            "grounded": True,
            "requires_human_review": True,
        }

    monkeypatch.setattr(
        "app.services.gmail_service.GmailService.list_new_messages", fake_list_new_messages
    )
    monkeypatch.setattr("app.services.gmail_service.GmailService.get_message", fake_get_message)
    monkeypatch.setattr("app.services.triage_service.TriageService.classify", fake_classify)
    monkeypatch.setattr("app.services.draft_service.DraftService.generate", fake_generate)


# --- _pull_gmail_async (pure async logic, injectable session_factory) -------


async def test_pull_gmail_async_processes_new_messages(db_session, session_factory, monkeypatch):
    user = await _user(db_session)
    await _link_google(db_session, user)
    _mock_pipeline(monkeypatch)

    summary = await workflow_tasks._pull_gmail_async(
        str(user.id), 12, workflow_tasks.DEFAULT_PULL_QUERY, session_factory=session_factory
    )

    assert summary["created"] == 1
    assert summary["scanned"] == 1


async def test_pull_gmail_async_missing_user_raises(session_factory):
    with pytest.raises(ValueError, match="not found"):
        await workflow_tasks._pull_gmail_async(
            str(uuid.uuid4()), 12, workflow_tasks.DEFAULT_PULL_QUERY, session_factory=session_factory
        )


async def test_pull_gmail_async_propagates_not_connected(db_session, session_factory):
    user = await _user(db_session, "no-gmail@firstmed.com")  # no GoogleCredential linked
    with pytest.raises(GmailNotConnectedError):
        await workflow_tasks._pull_gmail_async(
            str(user.id), 12, workflow_tasks.DEFAULT_PULL_QUERY, session_factory=session_factory
        )


async def test_list_connected_user_ids_only_includes_linked_accounts(db_session, session_factory):
    connected = await _user(db_session, "connected@firstmed.com")
    await _link_google(db_session, connected)
    await _user(db_session, "not-connected@firstmed.com")

    ids = await workflow_tasks._list_connected_user_ids_async(session_factory=session_factory)

    assert ids == [str(connected.id)]


# --- Celery task wrappers (registration + asyncio bridge + retry classification) --


def test_pull_gmail_task_is_registered():
    assert "workflow.pull_gmail" in workflow_tasks.celery_app.tasks
    assert "workflow.pull_all_connected" in workflow_tasks.celery_app.tasks


def test_pull_gmail_task_bridges_to_async_logic(monkeypatch):
    seen = {}

    async def fake_pull_gmail_async(user_id, max_results, query, **kwargs):
        seen["args"] = (user_id, max_results, query)
        return {"created": 1, "skipped": 0, "failed": 0, "scanned": 1}

    monkeypatch.setattr(workflow_tasks, "_pull_gmail_async", fake_pull_gmail_async)

    result = workflow_tasks.pull_gmail_task("user-123", 7, "custom query")

    assert result == {"created": 1, "skipped": 0, "failed": 0, "scanned": 1}
    assert seen["args"] == ("user-123", 7, "custom query")


def test_pull_gmail_task_permanent_error_is_not_retried(monkeypatch):
    async def raise_not_connected(*args, **kwargs):
        raise GmailNotConnectedError("no google account linked")

    monkeypatch.setattr(workflow_tasks, "_pull_gmail_async", raise_not_connected)

    with pytest.raises(GmailNotConnectedError):
        workflow_tasks.pull_gmail_task("user-123")


def test_pull_gmail_task_ai_not_configured_is_not_retried(monkeypatch):
    async def raise_ai_not_configured(*args, **kwargs):
        raise AINotConfiguredError("no API key")

    monkeypatch.setattr(workflow_tasks, "_pull_gmail_async", raise_ai_not_configured)

    with pytest.raises(AINotConfiguredError):
        workflow_tasks.pull_gmail_task("user-123")


def test_pull_gmail_task_retryable_error_goes_through_retry_path(monkeypatch, capsys):
    # A transient Gmail API error must go through self.retry() (not fail
    # outright via the permanent-error branch). Celery's retry(exc=...), when
    # invoked outside a real worker dispatch (no broker needed here), re-raises
    # the ORIGINAL exception rather than a generic Retry — so which branch ran
    # is verified via the distinct log event each one emits (structlog prints
    # straight to stdout, hence capsys rather than caplog).
    async def raise_gmail_api_error(*args, **kwargs):
        raise GmailApiError("503 from Gmail")

    monkeypatch.setattr(workflow_tasks, "_pull_gmail_async", raise_gmail_api_error)

    with pytest.raises(GmailApiError):
        workflow_tasks.pull_gmail_task("user-123")

    assert "workflow.pull_task_retrying" in capsys.readouterr().out


# --- pull_all_connected_task (fan-out) ---------------------------------------


def test_pull_all_connected_task_enqueues_one_task_per_connected_user(monkeypatch):
    async def fake_list_ids(**kwargs):
        return ["uid-1", "uid-2", "uid-3"]

    enqueued = []

    def fake_delay(user_id, max_results, query):
        enqueued.append((user_id, max_results, query))

    monkeypatch.setattr(workflow_tasks, "_list_connected_user_ids_async", fake_list_ids)
    monkeypatch.setattr(workflow_tasks.pull_gmail_task, "delay", fake_delay)

    result = workflow_tasks.pull_all_connected_task(max_results=5)

    assert result == {"enqueued": 3}
    assert enqueued == [
        ("uid-1", 5, workflow_tasks.DEFAULT_PULL_QUERY),
        ("uid-2", 5, workflow_tasks.DEFAULT_PULL_QUERY),
        ("uid-3", 5, workflow_tasks.DEFAULT_PULL_QUERY),
    ]
