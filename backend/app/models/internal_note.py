"""InternalNote model for cross-department collaboration."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import ForeignKey, String, Text, Uuid, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class InternalNote(Base, TimestampMixin):
    __tablename__ = "internal_notes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    author_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    author_role: Mapped[str] = mapped_column(String(50), nullable=False, default="FRONT_OFFICE")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    mentioned_department: Mapped[str | None] = mapped_column(String(50), nullable=True)

    author = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<InternalNote id={self.id} email_id={self.email_id!r} author_id={self.author_id}>"
