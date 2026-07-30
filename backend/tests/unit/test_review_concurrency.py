"""Unit tests for shared-inbox concurrency safety (requirement G).

Covers two independent guarantees:
  1. A DB-level unique constraint on (user_id, gmail_message_id) prevents two
     concurrent pulls from creating duplicate review rows for the same email.
  2. Atomic status-claiming (`claim_status`) prevents two concurrent approve/
     send requests from both reaching the Gmail API for the same review.
"""

from __future__ import annotations

import pytest
from app.models.user import User
from app.repositories.draft_review import (
    DraftReviewRepository,
    DuplicateReviewError,
    StaleReviewStatusError,
)
from app.schemas.review import ReviewStatus
from app.services.workflow_service import WorkflowService


async def _user(db_session, email="conc@firstmed.com") -> User:
    user = User(email=email, full_name="Conc")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _seed_review(db_session, user, *, status=ReviewStatus.pending.value, **overrides):
    repo = DraftReviewRepository(db_session)
    fields = {
        "user_id": user.id,
        "gmail_message_id": "msg-1",
        "gmail_thread_id": "t1",
        "message_id_header": "<orig@mail.gmail.com>",
        "sender": "patient@example.com",
        "subject": "Refill",
        "intent": "prescription_refill",
        "urgency": "normal",
        "department": "nurse",
        "classification": "ADMIN_DIRECT_REPLY",
        "confidence": 0.9,
        "draft_body": "Draft reply. The FirstMed Team",
        "status": status,
    }
    fields.update(overrides)
    return await repo.create(**fields)


# --- unique constraint: duplicate review rows -------------------------------


async def test_duplicate_gmail_message_id_raises(db_session):
    user = await _user(db_session)
    await _seed_review(db_session, user)
    with pytest.raises(DuplicateReviewError):
        await _seed_review(db_session, user)  # same user + same gmail_message_id


async def test_same_message_id_different_users_is_allowed(db_session):
    # The shared inbox may be linked by more than one staff account; the
    # constraint is scoped to (user, message), not message alone.
    user_a = await _user(db_session, "a@firstmed.com")
    user_b = await _user(db_session, "b@firstmed.com")
    await _seed_review(db_session, user_a)
    await _seed_review(db_session, user_b)  # same message id, different user — OK


# --- atomic status claim: approve/send double-action race -------------------


async def test_claim_status_second_caller_gets_stale_error(db_session):
    user = await _user(db_session)
    review = await _seed_review(db_session, user)
    repo = DraftReviewRepository(db_session)

    claimed = await repo.claim_status(
        review.id,
        from_statuses=[ReviewStatus.pending.value],
        to_status=ReviewStatus.approved.value,
    )
    assert claimed.status == ReviewStatus.approved.value

    # A second concurrent caller attempting the same transition finds the row
    # already moved — this is the race-safety guarantee itself.
    with pytest.raises(StaleReviewStatusError):
        await repo.claim_status(
            review.id,
            from_statuses=[ReviewStatus.pending.value],
            to_status=ReviewStatus.approved.value,
        )


async def test_approve_race_only_one_caller_reaches_gmail(db_session, monkeypatch):
    calls = {"create_draft": 0}

    async def fake_create_draft(self, user, **kwargs):
        calls["create_draft"] += 1
        return {"draft_id": "draft-1", "message_id": "m9", "thread_id": "t1"}

    monkeypatch.setattr("app.services.gmail_service.GmailService.create_draft", fake_create_draft)

    user = await _user(db_session)
    review = await _seed_review(db_session, user)
    wf = WorkflowService(db_session)

    # First caller wins.
    updated = await wf.approve(user, review)
    assert updated.status == ReviewStatus.approved.value
    assert calls["create_draft"] == 1

    # Second caller (racing, or a stale retry) must be rejected BEFORE Gmail is
    # ever called again — no second Gmail draft is created.
    with pytest.raises(StaleReviewStatusError):
        await wf.approve(user, review)
    assert calls["create_draft"] == 1


async def test_approve_reverts_status_on_gmail_failure(db_session, monkeypatch):
    async def failing_create_draft(self, user, **kwargs):
        raise RuntimeError("Gmail is down")

    monkeypatch.setattr(
        "app.services.gmail_service.GmailService.create_draft", failing_create_draft
    )

    user = await _user(db_session)
    review = await _seed_review(db_session, user)
    wf = WorkflowService(db_session)

    with pytest.raises(RuntimeError):
        await wf.approve(user, review)

    # The claim must be reverted so the review is retryable, not stuck
    # "approved" with no Gmail draft ever created.
    repo = DraftReviewRepository(db_session)
    reloaded = await repo.get(review.id)
    assert reloaded.status == ReviewStatus.pending.value


async def test_send_race_only_one_caller_reaches_gmail(db_session, monkeypatch):
    calls = {"send_draft": 0}

    async def fake_send_draft(self, user, draft_id):
        calls["send_draft"] += 1
        return {"message_id": "sent-1", "thread_id": "t1", "label_ids": ["SENT"]}

    monkeypatch.setattr("app.services.gmail_service.GmailService.send_draft", fake_send_draft)

    user = await _user(db_session)
    review = await _seed_review(
        db_session, user, status=ReviewStatus.approved.value, gmail_draft_id="draft-1"
    )
    wf = WorkflowService(db_session)

    updated = await wf.send(user, review)
    assert updated.status == ReviewStatus.sent.value
    assert calls["send_draft"] == 1

    with pytest.raises(StaleReviewStatusError):
        await wf.send(user, review)
    assert calls["send_draft"] == 1  # second racer never reached Gmail


async def test_send_reverts_to_approved_on_gmail_failure(db_session, monkeypatch):
    async def failing_send_draft(self, user, draft_id):
        raise RuntimeError("Gmail is down")

    monkeypatch.setattr("app.services.gmail_service.GmailService.send_draft", failing_send_draft)

    user = await _user(db_session)
    review = await _seed_review(
        db_session, user, status=ReviewStatus.approved.value, gmail_draft_id="draft-1"
    )
    wf = WorkflowService(db_session)

    with pytest.raises(RuntimeError):
        await wf.send(user, review)

    repo = DraftReviewRepository(db_session)
    reloaded = await repo.get(review.id)
    assert reloaded.status == ReviewStatus.approved.value


async def test_reject_race_second_caller_gets_stale_error(db_session):
    user = await _user(db_session)
    review = await _seed_review(db_session, user)
    wf = WorkflowService(db_session)

    updated = await wf.reject(user, review, "not needed")
    assert updated.status == ReviewStatus.rejected.value

    with pytest.raises(StaleReviewStatusError):
        await wf.reject(user, review, "too late")
