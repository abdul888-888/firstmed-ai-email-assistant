"""Internal collaboration engine (Phase 11): review assignment + notes."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.draft_review import DraftReview
from app.models.review_note import ReviewNote
from app.models.user import User
from app.repositories.draft_review import DraftReviewRepository
from app.repositories.review_note import ReviewNoteRepository
from app.repositories.user import UserRepository

logger = get_logger(__name__)


class CollaborationError(Exception):
    """Base error for the collaboration service."""


class AssigneeNotFoundError(CollaborationError):
    """Raised when assigning a review to a user that doesn't exist or is inactive."""


class CollaborationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.reviews = DraftReviewRepository(session)
        self.notes = ReviewNoteRepository(session)
        self.users = UserRepository(session)

    async def assign(self, review: DraftReview, assigned_to: uuid.UUID | None) -> DraftReview:
        """Hand a review off to ``assigned_to`` (or clear the assignment if ``None``)."""
        if assigned_to is not None:
            assignee = await self.users.get_by_id(assigned_to)
            if assignee is None or not assignee.is_active:
                raise AssigneeNotFoundError(f"No active user with id {assigned_to}")
        updated = await self.reviews.assign(review, assigned_to=assigned_to)
        logger.info(
            "collaboration.assigned",
            review_id=str(review.id),
            assigned_to=str(assigned_to) if assigned_to else None,
        )
        return updated

    async def add_note(self, review: DraftReview, author: User, body: str) -> ReviewNote:
        note = await self.notes.create(review_id=review.id, author_id=author.id, body=body)
        logger.info("collaboration.note_added", review_id=str(review.id), author_id=str(author.id))
        return note

    async def list_notes(self, review: DraftReview) -> list[ReviewNote]:
        return await self.notes.list_by_review(review.id)
