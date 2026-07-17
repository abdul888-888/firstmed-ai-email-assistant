"""Data-access layer for :class:`~app.models.draft_review.DraftReview`."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft_review import DraftReview
from app.schemas.review import ReviewStatus


class DraftReviewRepository:
    """Persistence for workflow-produced review records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, review_id: uuid.UUID) -> DraftReview | None:
        return await self.session.get(DraftReview, review_id)

    async def create(self, **fields: Any) -> DraftReview:
        review = DraftReview(**fields)
        self.session.add(review)
        await self.session.commit()
        await self.session.refresh(review)
        return review

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
        gmail_draft_id: str,
        reviewed_by: uuid.UUID,
    ) -> DraftReview:
        review.status = ReviewStatus.approved.value
        review.gmail_draft_id = gmail_draft_id
        review.reviewed_by = reviewed_by
        review.reviewed_at = dt.datetime.now(dt.UTC)
        await self.session.commit()
        await self.session.refresh(review)
        return review
