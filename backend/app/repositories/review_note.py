"""Data-access layer for :class:`~app.models.review_note.ReviewNote`."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review_note import ReviewNote


class ReviewNoteRepository:
    """Persistence for internal collaboration notes on a review."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **fields: Any) -> ReviewNote:
        note = ReviewNote(**fields)
        self.session.add(note)
        await self.session.commit()
        await self.session.refresh(note)
        return note

    async def list_by_review(self, review_id: uuid.UUID) -> list[ReviewNote]:
        """Notes on a review, oldest first (chronological thread)."""
        result = await self.session.execute(
            select(ReviewNote)
            .where(ReviewNote.review_id == review_id)
            .order_by(ReviewNote.created_at.asc())
        )
        return list(result.scalars().all())
