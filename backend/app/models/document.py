"""Unified retrieval index.

A ``Document`` is a normalized, searchable copy of content ingested from an
external source (Gmail message, Notion page/database). Phase 4 supports lexical
search over these rows; Phase 5 adds embeddings for semantic retrieval.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import JSON, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DocumentSource(str, enum.Enum):
    gmail = "gmail"
    notion = "notion"


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        # A source item is indexed once; re-ingesting updates the same row.
        Index("uq_documents_source_item", "source", "source_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # Semantic-retrieval vector (Phase 9). Stored as a JSON array for
    # SQLite/PostgreSQL portability; ``embedding_model`` records which model
    # produced it so stale vectors can be re-embedded on a model change.
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Document source={self.source} source_id={self.source_id!r}>"
