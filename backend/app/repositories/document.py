"""Data-access layer for :class:`~app.models.document.Document`."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document

__all__ = ["DocumentRepository"]


class DocumentRepository:
    """Persistence + candidate retrieval for the unified document index."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, document_id: uuid.UUID) -> Document | None:
        return await self.session.get(Document, document_id)

    async def get_by_source(self, source: str, source_id: str) -> Document | None:
        result = await self.session.execute(
            select(Document).where(Document.source == source, Document.source_id == source_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        source: str,
        source_id: str,
        title: str,
        content: str,
        url: str | None = None,
        doc_metadata: dict[str, Any] | None = None,
    ) -> Document:
        """Insert or update the row identified by ``(source, source_id)``."""
        doc = await self.get_by_source(source, source_id)
        if doc is None:
            doc = Document(source=source, source_id=source_id)
            self.session.add(doc)

        doc.title = title
        doc.content = content
        doc.url = url
        doc.doc_metadata = doc_metadata or {}

        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def list_needing_embedding(self, model: str, *, limit: int = 1000) -> list[Document]:
        """Documents with no embedding, or one from a different model (stale)."""
        result = await self.session.execute(
            select(Document)
            .where(
                or_(
                    Document.embedding.is_(None),
                    Document.embedding_model.is_(None),
                    Document.embedding_model != model,
                )
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def set_embedding(
        self, doc: Document, *, embedding: list[float], model: str
    ) -> Document:
        doc.embedding = embedding
        doc.embedding_model = model
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def counts_by_source(self) -> dict[str, int]:
        result = await self.session.execute(
            select(Document.source, func.count()).group_by(Document.source)
        )
        return dict(result.all())

    async def fetch_candidates(
        self, terms: list[str], *, sources: list[str] | None = None, limit: int = 200
    ) -> list[Document]:
        """Return rows matching any term (case-insensitive) for in-memory ranking.

        With no terms, returns the most recently updated rows (browse mode).
        """
        stmt = select(Document)
        if sources:
            stmt = stmt.where(Document.source.in_(sources))
        if terms:
            stmt = stmt.where(
                or_(
                    *[
                        or_(
                            Document.title.ilike(f"%{term}%"),
                            Document.content.ilike(f"%{term}%"),
                        )
                        for term in terms
                    ]
                )
            )
        else:
            stmt = stmt.order_by(Document.updated_at.desc())
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
