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
        """Index Notion pages the integration can see (databases: title only)."""
        results = await self.notion.search(query, page_size=page_size)
        count = 0
        for item in results.get("results", []):
            title = item.get("title") or "(untitled)"
            content = title
            if item.get("object") == "page":
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
                    "object": item.get("object", ""),
                    "last_edited_time": item.get("last_edited_time", ""),
                },
            )
            count += 1
        logger.info("ingest.notion", indexed=count)
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

        return {
            "gmail_indexed": gmail_indexed,
            "notion_indexed": notion_indexed,
            "notes": notes,
        }
