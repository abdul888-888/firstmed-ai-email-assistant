"""Internal collaboration note attached to a :class:`~app.models.draft_review.DraftReview`.

Phase 11: staff can leave notes on a review (e.g. handoff context, a question
for the assignee) independent of the ``review_note`` reject-reason field on
``DraftReview`` itself, which is reserved for the single reviewer-facing
rejection message.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ReviewNote(Base, TimestampMixin):
    __tablename__ = "review_notes"
    __table_args__ = (Index("ix_review_notes_review_id", "review_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("draft_reviews.id"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ReviewNote id={self.id} review_id={self.review_id}>"
