"""Data-access layer for :class:`~app.models.draft_review.DraftReview`."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft_review import DraftReview
from app.schemas.review import ReviewStatus


class DuplicateReviewError(Exception):
    """Raised when a (user_id, provider_message_id) review already exists.

    Surfaces the DB-level unique constraint as a typed error so callers (the
    pull loop, the direct single-message endpoint) can treat a race as a
    benign "already processed" rather than an unexpected failure.
    """


class StaleReviewStatusError(Exception):
    """Raised when an atomic status transition finds the review already moved.

    Means a concurrent request (another staff member, or a retry) won the race
    to act on this review first.
    """


class DraftReviewRepository:
    """Persistence for workflow-produced review records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, review_id: uuid.UUID) -> DraftReview | None:
        return await self.session.get(DraftReview, review_id)

    async def create(self, **fields: Any) -> DraftReview:
        review = DraftReview(**fields)
        self.session.add(review)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise DuplicateReviewError(
                f"A review already exists for user={fields.get('user_id')} "
                f"provider_message_id={fields.get('provider_message_id')!r}"
            ) from exc
        await self.session.refresh(review)
        return review

    async def claim_status(
        self, review_id: uuid.UUID, *, from_statuses: list[str], to_status: str
    ) -> DraftReview:
        """Atomically transition ``review_id`` from one of ``from_statuses`` to
        ``to_status`` and return the updated row.

        Uses a single ``UPDATE ... WHERE id = :id AND status IN (:from_statuses)``
        so the transition is race-safe under concurrent requests: if two staff
        (or a double-click) both attempt the same action, only one UPDATE
        matches a row — the other affects zero rows and raises
        :class:`StaleReviewStatusError`. Callers MUST claim before performing any
        outward-facing side effect (e.g. a Gmail API call) so at most one
        concurrent caller ever reaches that side effect.
        """
        stmt = (
            update(DraftReview)
            .where(DraftReview.id == review_id, DraftReview.status.in_(from_statuses))
            .values(status=to_status)
        )
        result = await self.session.execute(stmt)
        if result.rowcount == 0:
            await self.session.rollback()
            raise StaleReviewStatusError(
                f"Review {review_id} is not in one of {from_statuses} "
                "(already acted on by another request)."
            )
        await self.session.commit()
        review = await self.get(review_id)
        assert review is not None  # just updated within this transaction
        # The UPDATE above went through Core, bypassing the ORM's identity map —
        # with expire_on_commit=False (this app's session config), ``get()`` can
        # return the SAME cached, now-stale Python object. Force a real reload so
        # callers see the new status, not whatever was cached before the claim.
        await self.session.refresh(review)
        return review

    async def existing_message_ids(self, user_id: uuid.UUID) -> set[str]:
        """Provider message IDs this user already has a review for (any status).

        Used by the pull workflow to skip messages already triaged so a
        repeated pull is idempotent and never creates duplicate review cards.
        """
        result = await self.session.execute(
            select(DraftReview.provider_message_id).where(DraftReview.user_id == user_id)
        )
        return {mid for mid in result.scalars().all() if mid}

    async def list_pending(self, user_id: uuid.UUID, *, limit: int = 50) -> list[DraftReview]:
        """Pending reviews for a user, newest first."""
        return await self.list_by_status(user_id, ReviewStatus.pending.value, limit=limit)

    async def list_by_status(
        self, user_id: uuid.UUID, status: str, *, limit: int = 50
    ) -> list[DraftReview]:
        """Reviews for a user filtered by status, newest first."""
        result = await self.session.execute(
            select(DraftReview)
            .where(DraftReview.user_id == user_id, DraftReview.status == status)
            .order_by(DraftReview.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_body(self, review: DraftReview, *, draft_body: str) -> DraftReview:
        review.draft_body = draft_body
        await self.session.commit()
        await self.session.refresh(review)
        return review

    async def mark_rejected(
        self, review: DraftReview, *, reviewed_by: uuid.UUID, note: str
    ) -> DraftReview:
        review.status = ReviewStatus.rejected.value
        review.review_note = note
        review.reviewed_by = reviewed_by
        review.reviewed_at = dt.datetime.now(dt.UTC)
        await self.session.commit()
        await self.session.refresh(review)
        return review

    async def mark_sent(self, review: DraftReview, *, sent_message_id: str) -> DraftReview:
        review.status = ReviewStatus.sent.value
        review.sent_message_id = sent_message_id
        review.sent_at = dt.datetime.now(dt.UTC)
        await self.session.commit()
        await self.session.refresh(review)
        return review

    async def mark_approved(
        self,
        review: DraftReview,
        *,
        provider_draft_id: str,
        reviewed_by: uuid.UUID,
    ) -> DraftReview:
        review.status = ReviewStatus.approved.value
        review.provider_draft_id = provider_draft_id
        review.reviewed_by = reviewed_by
        review.reviewed_at = dt.datetime.now(dt.UTC)
        await self.session.commit()
        await self.session.refresh(review)
        return review

    async def assign(self, review: DraftReview, *, assigned_to: uuid.UUID | None) -> DraftReview:
        review.assigned_to = assigned_to
        await self.session.commit()
        await self.session.refresh(review)
        return review

    async def add_specialist_input(
        self, review: DraftReview, *, specialist_input: str, specialist_id: uuid.UUID
    ) -> DraftReview:
        """Record specialist input for an escalated review."""
        review.specialist_input = specialist_input
        review.specialist_id = specialist_id
        review.specialist_input_at = dt.datetime.now(dt.UTC)
        review.status = ReviewStatus.specialist_input_received.value
        await self.session.commit()
        await self.session.refresh(review)
        return review

    async def list_awaiting_specialist(
        self, user_id: uuid.UUID, *, limit: int = 50
    ) -> list[DraftReview]:
        """Reviews awaiting specialist input."""
        return await self.list_by_status(
            user_id, ReviewStatus.awaiting_specialist_input.value, limit=limit
        )

    async def list_specialist_input_received(
        self, user_id: uuid.UUID, *, limit: int = 50
    ) -> list[DraftReview]:
        """Reviews with specialist input received, awaiting draft revision."""
        return await self.list_by_status(
            user_id, ReviewStatus.specialist_input_received.value, limit=limit
        )
