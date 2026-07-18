"""Tests for the Phase 11 internal collaboration engine: assignment + notes."""

from __future__ import annotations

import uuid

import pytest
from app.models.user import UserRole
from app.repositories.draft_review import DraftReviewRepository
from app.repositories.review_note import ReviewNoteRepository
from app.repositories.user import UserRepository
from app.services.collaboration_service import AssigneeNotFoundError, CollaborationService


async def _seed_review(db_session, *, user_id):
    repo = DraftReviewRepository(db_session)
    return await repo.create(
        user_id=user_id,
        gmail_message_id="msg-1",
        intent="prescription_refill",
        urgency="normal",
        department="nurse",
        classification="ADMIN_DIRECT_REPLY",
    )


async def _seed_user(db_session, email, *, role=UserRole.front_office, is_active=True):
    user = await UserRepository(db_session).create(
        email=email, hashed_password="x", full_name="U", role=role
    )
    if not is_active:
        user.is_active = False
        await db_session.commit()
        await db_session.refresh(user)
    return user


async def _register(client, email: str, role: str = "front_office") -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "N", "role": role},
    )
    user_id = resp.json()["id"]
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login.json()["access_token"], user_id


# --- repository --------------------------------------------------------------


async def test_repo_assign_sets_and_clears(db_session):
    owner = await _seed_user(db_session, "repo-owner@firstmed.com")
    assignee = await _seed_user(db_session, "repo-assignee@firstmed.com")
    review = await _seed_review(db_session, user_id=owner.id)

    repo = DraftReviewRepository(db_session)
    assigned = await repo.assign(review, assigned_to=assignee.id)
    assert assigned.assigned_to == assignee.id

    cleared = await repo.assign(review, assigned_to=None)
    assert cleared.assigned_to is None


async def test_repo_notes_create_and_list_chronological(db_session):
    owner = await _seed_user(db_session, "repo-notes-owner@firstmed.com")
    review = await _seed_review(db_session, user_id=owner.id)

    notes_repo = ReviewNoteRepository(db_session)
    first = await notes_repo.create(review_id=review.id, author_id=owner.id, body="First note")
    second = await notes_repo.create(review_id=review.id, author_id=owner.id, body="Second note")

    notes = await notes_repo.list_by_review(review.id)
    assert [n.id for n in notes] == [first.id, second.id]
    assert [n.body for n in notes] == ["First note", "Second note"]


# --- service -------------------------------------------------------------------


async def test_service_assign_rejects_unknown_user(db_session):
    owner = await _seed_user(db_session, "svc-owner1@firstmed.com")
    review = await _seed_review(db_session, user_id=owner.id)

    with pytest.raises(AssigneeNotFoundError):
        await CollaborationService(db_session).assign(review, uuid.uuid4())


async def test_service_assign_rejects_inactive_user(db_session):
    owner = await _seed_user(db_session, "svc-owner2@firstmed.com")
    inactive = await _seed_user(db_session, "svc-inactive@firstmed.com", is_active=False)
    review = await _seed_review(db_session, user_id=owner.id)

    with pytest.raises(AssigneeNotFoundError):
        await CollaborationService(db_session).assign(review, inactive.id)


async def test_service_assign_and_add_note(db_session):
    owner = await _seed_user(db_session, "svc-owner3@firstmed.com")
    assignee = await _seed_user(db_session, "svc-assignee3@firstmed.com")
    review = await _seed_review(db_session, user_id=owner.id)

    service = CollaborationService(db_session)
    updated = await service.assign(review, assignee.id)
    assert updated.assigned_to == assignee.id

    note = await service.add_note(review, owner, "Please double check dosage.")
    assert note.review_id == review.id
    assert note.author_id == owner.id

    notes = await service.list_notes(review)
    assert len(notes) == 1
    assert notes[0].body == "Please double check dosage."


# --- API -------------------------------------------------------------------


async def test_admin_status(client):
    resp = await client.get("/api/v1/admin/status")
    assert resp.status_code == 200
    assert resp.json() == {"module": "admin", "implemented": True, "phase": 11}


async def test_list_users_requires_auth(client):
    resp = await client.get("/api/v1/admin/users")
    assert resp.status_code == 401


async def test_list_users_returns_active_only(client, db_session):
    token, _ = await _register(client, "api-users1@firstmed.com")
    await _seed_user(db_session, "api-users-inactive@firstmed.com", is_active=False)

    resp = await client.get(
        "/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    emails = {u["email"] for u in body["users"]}
    assert "api-users1@firstmed.com" in emails
    assert "api-users-inactive@firstmed.com" not in emails
    assert body["count"] == len(body["users"])


async def test_assign_requires_auth(client):
    resp = await client.patch(
        "/api/v1/admin/reviews/00000000-0000-0000-0000-000000000000/assign",
        json={"assigned_to": None},
    )
    assert resp.status_code == 401


async def test_assign_unknown_review_404(client):
    token, _ = await _register(client, "api-adm1@firstmed.com")
    resp = await client.patch(
        "/api/v1/admin/reviews/00000000-0000-0000-0000-000000000000/assign",
        json={"assigned_to": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_assign_to_unknown_user_422(client, db_session):
    token, owner_id = await _register(client, "api-adm2@firstmed.com")
    review = await _seed_review(db_session, user_id=uuid.UUID(owner_id))

    resp = await client.patch(
        f"/api/v1/admin/reviews/{review.id}/assign",
        json={"assigned_to": "00000000-0000-0000-0000-000000000000"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


async def test_assign_and_unassign_review(client, db_session):
    token, owner_id = await _register(client, "api-adm3-owner@firstmed.com")
    _, assignee_id = await _register(client, "api-adm3-assignee@firstmed.com")
    review = await _seed_review(db_session, user_id=uuid.UUID(owner_id))
    h = {"Authorization": f"Bearer {token}"}

    resp = await client.patch(
        f"/api/v1/admin/reviews/{review.id}/assign",
        json={"assigned_to": assignee_id},
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["assigned_to"] == assignee_id

    resp2 = await client.patch(
        f"/api/v1/admin/reviews/{review.id}/assign",
        json={"assigned_to": None},
        headers=h,
    )
    assert resp2.status_code == 200
    assert resp2.json()["assigned_to"] is None


async def test_assign_works_across_users_not_just_owner(client, db_session):
    # The collaboration surface loads a review by id regardless of who "owns"
    # it — unlike /reviews, which scopes strictly to the requesting user.
    _, owner_id = await _register(client, "api-adm4-owner@firstmed.com")
    other_token, assignee_id = await _register(client, "api-adm4-other@firstmed.com")
    review = await _seed_review(db_session, user_id=uuid.UUID(owner_id))

    resp = await client.patch(
        f"/api/v1/admin/reviews/{review.id}/assign",
        json={"assigned_to": assignee_id},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["assigned_to"] == assignee_id


async def test_notes_requires_auth(client):
    resp = await client.get("/api/v1/admin/reviews/00000000-0000-0000-0000-000000000000/notes")
    assert resp.status_code == 401


async def test_notes_unknown_review_404(client):
    token, _ = await _register(client, "api-adm5@firstmed.com")
    resp = await client.get(
        "/api/v1/admin/reviews/00000000-0000-0000-0000-000000000000/notes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_add_and_list_notes(client, db_session):
    token, owner_id = await _register(client, "api-adm6@firstmed.com")
    review = await _seed_review(db_session, user_id=uuid.UUID(owner_id))
    h = {"Authorization": f"Bearer {token}"}

    empty = await client.get(f"/api/v1/admin/reviews/{review.id}/notes", headers=h)
    assert empty.status_code == 200
    assert empty.json() == {"notes": [], "count": 0}

    resp1 = await client.post(
        f"/api/v1/admin/reviews/{review.id}/notes", json={"body": "First note"}, headers=h
    )
    assert resp1.status_code == 201
    assert resp1.json()["body"] == "First note"
    assert resp1.json()["author_id"] == owner_id

    resp2 = await client.post(
        f"/api/v1/admin/reviews/{review.id}/notes", json={"body": "Second note"}, headers=h
    )
    assert resp2.status_code == 201

    listing = await client.get(f"/api/v1/admin/reviews/{review.id}/notes", headers=h)
    assert listing.status_code == 200
    body = listing.json()
    assert body["count"] == 2
    assert [n["body"] for n in body["notes"]] == ["First note", "Second note"]


async def test_add_note_empty_body_rejected(client, db_session):
    token, owner_id = await _register(client, "api-adm7@firstmed.com")
    review = await _seed_review(db_session, user_id=uuid.UUID(owner_id))
    h = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/api/v1/admin/reviews/{review.id}/notes", json={"body": ""}, headers=h
    )
    assert resp.status_code == 422
