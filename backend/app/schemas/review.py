"""Schemas for the workflow engine + review queue (Phase 6 / Phase 8 slice)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReviewClassification(str, enum.Enum):
    """Binary safety-gate outcome derived from triage."""

    ADMIN_DIRECT_REPLY = "ADMIN_DIRECT_REPLY"
    NEEDS_PHYSICIAN_REVIEW = "NEEDS_PHYSICIAN_REVIEW"


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    sent = "sent"


class ReviewCitation(BaseModel):
    document_id: str
    source: str
    title: str
    url: str | None = None


class ReviewEdit(BaseModel):
    """Inline edit of the drafted reply before approval."""

    draft_body: str = Field(min_length=1)


class ReviewReject(BaseModel):
    """Reject a pending review with a brief reason."""

    reason: str = Field(default="", max_length=2000)


class DraftReviewRead(BaseModel):
    """A persisted AI decision + draft awaiting (or past) human review."""

    id: uuid.UUID
    gmail_message_id: str
    gmail_thread_id: str = ""
    sender: str = ""
    subject: str = ""
    intent: str
    urgency: str
    department: str
    classification: ReviewClassification
    confidence: float
    summary: str = ""
    reason: str = ""
    draft_body: str = ""
    citations: list[ReviewCitation] = Field(default_factory=list)
    model: str = ""
    status: ReviewStatus
    gmail_draft_id: str | None = None
    review_note: str | None = None
    reviewed_at: datetime | None = None
    sent_at: datetime | None = None
    sent_message_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewList(BaseModel):
    reviews: list[DraftReviewRead] = Field(default_factory=list)
    count: int = 0
