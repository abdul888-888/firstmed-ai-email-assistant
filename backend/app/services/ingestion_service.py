"""Ingest Gmail + Notion content into the unified document index (Phase 4).

Read from the source services and upsert normalized :class:`Document` rows. Runs
synchronously here; moving it onto the Celery worker is a later-phase concern.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.document import DocumentSource
from app.models.user import User
from app.repositories.document import DocumentRepository
from app.services.embedding_service import EmbeddingService
from app.services.gmail_service import GmailNotConnectedError, GmailService
from app.services.notion_service import NotionService

logger = get_logger(__name__)


class IngestionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        gmail: GmailService | None = None,
        notion: NotionService | None = None,
    ) -> None:
        self.session = session
        self.repo = DocumentRepository(session)
        self.gmail = gmail or GmailService(session)
        self.notion = notion or NotionService()

    async def ingest_gmail(self, user: User, *, max_results: int = 25) -> int:
        """Index the user's shared-inbox messages. Raises if Gmail isn't linked."""
        listing = await self.gmail.list_messages(user, max_results=max_results)
        count = 0
        for summary in listing.get("messages", []):
            msg = await self.gmail.get_message(user, summary["id"])
            subject = msg.get("subject") or "(no subject)"
            body_parts = [subject, msg.get("from", ""), msg.get("snippet", "")]
            await self.repo.upsert(
                source=DocumentSource.gmail.value,
                source_id=msg["id"],
                title=subject,
                content="\n".join(p for p in body_parts if p),
                url=f"https://mail.google.com/mail/u/0/#all/{msg['id']}",
                doc_metadata={
                    "thread_id": msg.get("thread_id", ""),
                    "from": msg.get("from", ""),
                    "date": msg.get("date", ""),
                    "label_ids": msg.get("label_ids", []),
                },
            )
            count += 1
        logger.info("ingest.gmail", user_id=str(user.id), indexed=count)
        return count

    async def ingest_notion(self, *, query: str | None = None, page_size: int = 25) -> int:
        """Index Notion content the integration can see.

        Pages are indexed as title + block text. **Databases are expanded into
        their rows** — each row's typed properties (price, insurer, service, …)
        are flattened to text and indexed as its own document, so tabular
        knowledge like pricing/insurance tables becomes retrievable. Previously
        databases were indexed by title only, which is why pricing/insurance
        lookups returned nothing.
        """
        results = await self.notion.search(query, page_size=page_size)
        count = 0
        for item in results.get("results", []):
            obj = item.get("object", "")
            title = item.get("title") or "(untitled)"

            if obj == "database":
                count += await self._ingest_database(item)
                continue

            content = title
            if obj == "page":
                page_content = await self.notion.get_page_content(item["id"])
                block_text = "\n".join(
                    b["text"] for b in page_content.get("blocks", []) if b.get("text")
                )
                content = f"{title}\n{block_text}".strip()
            await self.repo.upsert(
                source=DocumentSource.notion.value,
                source_id=item["id"],
                title=title,
                content=content,
                url=item.get("url"),
                doc_metadata={
                    "object": obj,
                    "last_edited_time": item.get("last_edited_time", ""),
                },
            )
            count += 1
        logger.info("ingest.notion", indexed=count)
        return count

    async def _ingest_database(self, db_item: dict) -> int:
        """Index every row of a Notion database as an individual document."""
        db_title = db_item.get("title") or "(untitled database)"
        rows = await self.notion.query_database(db_item["id"])
        count = 0
        for row in rows.get("results", []):
            row_title = row.get("title") or db_title
            row_content = row.get("content", "")
            # Prefix the row title + parent database so a lexical/semantic query
            # like "how much is an MRI" matches the service name and its table.
            content = f"{row_title}\n{row_content}".strip() or row_title
            await self.repo.upsert(
                source=DocumentSource.notion.value,
                source_id=row["id"],
                title=row_title,
                content=content,
                url=row.get("url") or db_item.get("url"),
                doc_metadata={
                    "object": "database_row",
                    "database_id": db_item.get("id", ""),
                    "database_title": db_title,
                    "properties": row.get("properties", {}),
                    "last_edited_time": row.get("last_edited_time", ""),
                },
            )
            count += 1
        return count

    async def reindex(self, user: User) -> dict:
        """Ingest from every available source; skip unavailable ones gracefully."""
        notes: list[str] = []
        gmail_indexed = 0
        notion_indexed = 0

        try:
            gmail_indexed = await self.ingest_gmail(user)
        except GmailNotConnectedError:
            notes.append("gmail: not connected")

        if settings.notion_configured:
            notion_indexed = await self.ingest_notion()
        else:
            notes.append("notion: not configured")

        # Phase 9: embed any documents missing an up-to-date vector.
        embeddings = EmbeddingService(self.session)
        embeddings_indexed = await embeddings.backfill()
        if not embeddings.available:
            notes.append("embeddings: unavailable (lexical only)")

        return {
            "gmail_indexed": gmail_indexed,
            "notion_indexed": notion_indexed,
            "embeddings_indexed": embeddings_indexed,
            "notes": notes,
        }
