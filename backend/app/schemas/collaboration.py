"""Schemas for Phase 11 internal collaboration: review assignment + notes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReviewAssign(BaseModel):
    """Assign (or unassign, when ``assigned_to`` is ``None``) a review to a staff member."""

    assigned_to: uuid.UUID | None = None


class ReviewNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ReviewNoteRead(BaseModel):
    id: uuid.UUID
    review_id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewNoteList(BaseModel):
    notes: list[ReviewNoteRead] = Field(default_factory=list)
    count: int = 0
