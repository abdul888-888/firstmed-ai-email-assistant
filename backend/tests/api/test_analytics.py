"""Tests for the Phase 12 analytics dashboard: volume, response time, accuracy proxy."""

from __future__ import annotations

import datetime as dt

import pytest
from app.models.user import UserRole
from app.repositories.draft_review import DraftReviewRepository
from app.repositories.user import UserRepository
from app.services.analytics_service import AnalyticsService

BASE = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


async def _seed_user(db_session, email, *, role=UserRole.front_office):
    return await UserRepository(db_session).create(
        email=email, hashed_password="x", full_name="U", role=role
    )


async def _seed_review(db_session, *, user_id, department="nurse", **overrides):
    repo = DraftReviewRepository(db_session)
    review = await repo.create(
        user_id=user_id,
        gmail_message_id=overrides.pop("gmail_message_id", "msg-1"),
        intent=overrides.pop("intent", "prescription_refill"),
        urgency=overrides.pop("urgency", "normal"),
        department=department,
        classification=overrides.pop("classification", "ADMIN_DIRECT_REPLY"),
    )
    for key, value in overrides.items():
        setattr(review, key, value)
    await db_session.commit()
    await db_session.refresh(review)
    return review


async def _register(client, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "N", "role": "front_office"},
    )
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login.json()["access_token"]


# --- service -----------------------------------------------------------------


async def test_summary_empty(db_session):
    result = await AnalyticsService(db_session).summary()
    assert result["total_processed"] == 0
    assert result["counts_by_status"] == {}
    assert result["decided_count"] == 0
    assert result["triage_accuracy_rate"] is None
    assert result["avg_decision_seconds"] is None
    assert result["avg_turnaround_seconds"] is None


async def test_summary_computes_volume_accuracy_and_response_time(db_session):
    owner = await _seed_user(db_session, "an-owner@firstmed.com")

    await _seed_review(
        db_session,
        user_id=owner.id,
        gmail_message_id="m1",
        department="nurse",
        status="approved",
        created_at=BASE,
        reviewed_at=BASE + dt.timedelta(seconds=100),
    )
    await _seed_review(
        db_session,
        user_id=owner.id,
        gmail_message_id="m2",
        department="front_office",
        status="rejected",
        created_at=BASE,
        reviewed_at=BASE + dt.timedelta(seconds=300),
    )
    await _seed_review(
        db_session,
        user_id=owner.id,
        gmail_message_id="m3",
        department="nurse",
        status="sent",
        created_at=BASE,
        reviewed_at=BASE + dt.timedelta(seconds=200),
        sent_at=BASE + dt.timedelta(seconds=500),
    )
    await _seed_review(
        db_session,
        user_id=owner.id,
        gmail_message_id="m4",
        department="nurse",
        status="pending",
    )

    result = await AnalyticsService(db_session).summary()

    assert result["total_processed"] == 4
    assert result["counts_by_status"] == {
        "approved": 1,
        "rejected": 1,
        "sent": 1,
        "pending": 1,
    }
    assert result["counts_by_department"] == {"nurse": 3, "front_office": 1}
    assert result["decided_count"] == 3
    assert result["rejected_count"] == 1
    assert result["triage_accuracy_rate"] == pytest.approx(2 / 3)
    assert result["avg_decision_seconds"] == pytest.approx((100 + 300 + 200) / 3)
    assert result["avg_turnaround_seconds"] == pytest.approx(500)


async def test_summary_since_filters_by_created_at(db_session):
    owner = await _seed_user(db_session, "an-owner2@firstmed.com")
    old_cutoff = BASE - dt.timedelta(days=5)

    await _seed_review(
        db_session, user_id=owner.id, gmail_message_id="old", status="approved", created_at=old_cutoff
    )
    await _seed_review(
        db_session, user_id=owner.id, gmail_message_id="new", status="approved", created_at=BASE
    )

    all_time = await AnalyticsService(db_session).summary()
    assert all_time["total_processed"] == 2

    recent = await AnalyticsService(db_session).summary(since=BASE - dt.timedelta(days=1))
    assert recent["total_processed"] == 1


# --- API -------------------------------------------------------------------


async def test_analytics_status(client):
    resp = await client.get("/api/v1/analytics/status")
    assert resp.status_code == 200
    assert resp.json() == {"module": "analytics", "implemented": True, "phase": 12}


async def test_summary_requires_auth(client):
    resp = await client.get("/api/v1/analytics/summary")
    assert resp.status_code == 401


async def test_summary_endpoint_returns_metrics(client, db_session):
    token = await _register(client, "an-api@firstmed.com")
    owner = await UserRepository(db_session).get_by_email("an-api@firstmed.com")
    await _seed_review(
        db_session,
        user_id=owner.id,
        gmail_message_id="api-m1",
        status="approved",
        created_at=BASE,
        reviewed_at=BASE + dt.timedelta(seconds=60),
    )

    resp = await client.get(
        "/api/v1/analytics/summary", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_processed"] == 1
    assert body["counts_by_status"] == {"approved": 1}
    assert body["triage_accuracy_rate"] == 1.0
    assert body["avg_decision_seconds"] == pytest.approx(60)
