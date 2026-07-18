"""Persisted AI decision + draft record for the human-in-the-loop review queue.

A ``DraftReview`` is written by the Phase 6 workflow engine (one row per inbound
email it processes) and consumed by the Phase 8 review dashboard. It captures the
triage classification, safety-gate outcome, grounding citations, and the
generated draft — all *before* anything is written to Gmail. The draft only
becomes a Gmail draft when a human approves (``status`` → ``approved``).

Enum-valued fields (``intent``/``urgency``/``department``/``classification``/
``status``) are stored as plain strings for SQLite/PostgreSQL portability; their
allowed values live in ``app.schemas.ai`` and ``app.schemas.review`` and are
validated at write time (triage + safety gate) and re-typed on read (Pydantic).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.schemas.review import ReviewStatus


class DraftReview(Base, TimestampMixin):
    __tablename__ = "draft_reviews"
    __table_args__ = (
        Index("ix_draft_reviews_user_status", "user_id", "status"),
        Index("ix_draft_reviews_gmail_message_id", "gmail_message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )

    # --- source email ---
    gmail_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    gmail_thread_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    message_id_header: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sender: Mapped[str] = mapped_column(Text, nullable=False, default="")
    subject: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # --- triage + safety gate ---
    intent: Mapped[str] = mapped_column(String(32), nullable=False)
    urgency: Mapped[str] = mapped_column(String(32), nullable=False)
    department: Mapped[str] = mapped_column(String(32), nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # --- draft ---
    draft_body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    model: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    # --- review lifecycle ---
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ReviewStatus.pending.value, index=True
    )
    gmail_draft_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Phase 11: staff member this review has been handed off to for collaboration.
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    # Reviewer note (e.g. reject reason).
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set once the approved draft is sent via Gmail.
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<DraftReview id={self.id} status={self.status} "
            f"classification={self.classification}>"
        )
