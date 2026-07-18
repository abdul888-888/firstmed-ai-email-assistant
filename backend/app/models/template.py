"""Canned-response templates (Phase 7).

Reusable administrative reply snippets (office hours, parking, booking links,
etc.) that staff can insert into an AI draft on the review dashboard. ``key`` is
a stable slug for lookup/seeding; ``category`` groups them in the picker.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Template(Base, TimestampMixin):
    __tablename__ = "templates"
    __table_args__ = (Index("uq_templates_key", "key", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="general", index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Template key={self.key!r} category={self.category}>"
