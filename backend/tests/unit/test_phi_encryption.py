"""Verify PHI columns on DraftReview are actually encrypted at rest — not just
transparently round-tripped through the ORM (which would pass even if the
type decorator were a no-op)."""

from __future__ import annotations

from app.core import crypto
from app.models.draft_review import DraftReview
from app.models.user import User
from app.repositories.draft_review import DraftReviewRepository
from sqlalchemy import text


async def _user(db_session) -> User:
    user = User(email="phi@firstmed.com", full_name="Phi")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_phi_columns_are_ciphertext_in_the_database(db_session):
    user = await _user(db_session)
    review = await DraftReviewRepository(db_session).create(
        user_id=user.id,
        gmail_message_id="msg-1",
        intent="prescription_refill",
        urgency="normal",
        department="nurse",
        classification="ADMIN_DIRECT_REPLY",
        subject="Refill request",
        draft_body="Your refill will be ready in 48 hours.",
        summary="Patient asks about a prescription refill.",
        specialist_input="Approve the refill.",
    )

    # Raw SQL bypasses the ORM's type decorator entirely — this is what's
    # actually sitting in the database. Filter by gmail_message_id (a plain
    # string column) rather than id — the dialect-native UUID representation
    # (e.g. no dashes on SQLite) doesn't roundtrip through a bare text() bind.
    row = (
        await db_session.execute(
            text(
                "SELECT subject, draft_body, summary, specialist_input "
                "FROM draft_reviews WHERE gmail_message_id = :mid"
            ),
            {"mid": "msg-1"},
        )
    ).one()
    raw_subject, raw_draft_body, raw_summary, raw_specialist_input = row

    assert raw_subject != "Refill request"
    assert raw_draft_body != "Your refill will be ready in 48 hours."
    assert raw_summary != "Patient asks about a prescription refill."
    assert raw_specialist_input != "Approve the refill."

    # And it's genuinely Fernet ciphertext under the PHI key, not just mangled.
    assert crypto.decrypt_phi(raw_subject) == "Refill request"
    assert crypto.decrypt_phi(raw_draft_body) == "Your refill will be ready in 48 hours."
    assert crypto.decrypt_phi(raw_summary) == "Patient asks about a prescription refill."
    assert crypto.decrypt_phi(raw_specialist_input) == "Approve the refill."

    # The ORM path is fully transparent: reading back gives plaintext.
    reloaded = await db_session.get(DraftReview, review.id)
    assert reloaded.subject == "Refill request"
    assert reloaded.draft_body == "Your refill will be ready in 48 hours."
    assert reloaded.summary == "Patient asks about a prescription refill."
    assert reloaded.specialist_input == "Approve the refill."


async def test_phi_columns_allow_null_and_empty(db_session):
    user = await _user(db_session)
    review = await DraftReviewRepository(db_session).create(
        user_id=user.id,
        gmail_message_id="msg-2",
        intent="other",
        urgency="normal",
        department="front_office",
        classification="ROUTE_TO_STAFF",
        # subject/draft_body/summary default to "" ; specialist_input defaults to None
    )

    row = (
        await db_session.execute(
            text("SELECT subject, specialist_input FROM draft_reviews WHERE gmail_message_id = :mid"),
            {"mid": "msg-2"},
        )
    ).one()
    raw_subject, raw_specialist_input = row

    assert raw_specialist_input is None  # NULL passes through, never encrypted
    assert raw_subject is not None and raw_subject != ""  # "" is still encrypted
    assert crypto.decrypt_phi(raw_subject) == ""

    reloaded = await db_session.get(DraftReview, review.id)
    assert reloaded.subject == ""
    assert reloaded.specialist_input is None
