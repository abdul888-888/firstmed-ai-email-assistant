"""AI draft generation with retrieval context (Phase 5).

Retrieves relevant documents from the Phase 4 index (Notion SOPs / prior email),
feeds them to Claude as grounding context, and returns a DRAFT reply plus the
citations it was grounded on. Human-in-the-loop: the draft is never sent.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIClient, get_ai_client
from app.ai.prompts import DRAFT_SYSTEM, build_draft_user
from app.core.config import settings
from app.core.logging import get_logger
from app.models.user import User
from app.services.gmail_service import GmailService
from app.services.search_service import SearchService

logger = get_logger(__name__)

# Per-document content cap when assembling the context block, to bound prompt size.
_CONTEXT_CHARS_PER_DOC = 2000


class DraftService:
    def __init__(self, session: AsyncSession, ai: AIClient | None = None) -> None:
        self.session = session
        self.ai = ai or get_ai_client()
        self.search = SearchService(session)

    async def generate(
        self,
        subject: str,
        body: str,
        *,
        use_context: bool = True,
        max_context: int = 5,
    ) -> dict:
        citations: list[dict] = []
        context_parts: list[str] = []

        if use_context:
            hits = await self.search.search(f"{subject}\n{body}", limit=max_context)
            for hit in hits:
                doc = hit.document
                snippet = doc.content[:_CONTEXT_CHARS_PER_DOC]
                context_parts.append(f"[{doc.source}] {doc.title}\n{snippet}")
                citations.append(
                    {
                        "document_id": str(doc.id),
                        "source": doc.source,
                        "title": doc.title,
                        "url": doc.url,
                    }
                )

        draft = await self.ai.text(
            system=DRAFT_SYSTEM,
            user=build_draft_user(subject, body, "\n\n".join(context_parts)),
            max_tokens=settings.ai_max_tokens,
        )
        logger.info("ai.draft_generated", citations=len(citations))
        return {
            "draft": draft,
            "model": self.ai.model,
            "citations": citations,
            "requires_human_review": True,
        }


async def push_gmail_reply(session: AsyncSession, user: User, message_id: str) -> dict:
    """End-to-end pipeline: fetch a Gmail message, generate a grounded reply
    draft, and create it in the mailbox's Drafts folder (never sends).

    Propagates domain errors for the API layer to translate:
    ``GmailNotConnectedError`` / ``GmailApiError`` (from
    :mod:`app.services.gmail_service`) and ``AIError`` / ``AINotConfiguredError``
    (from :mod:`app.ai.client`).
    """
    gmail = GmailService(session)

    # a) Fetch the incoming patient email (full body, not just the snippet).
    msg = await gmail.get_message(user, message_id)
    subject = msg.get("subject", "")
    body = msg.get("body") or msg.get("snippet", "")
    sender = msg.get("from", "")

    # b) Run it through the RAG draft pipeline.
    draft = await DraftService(session).generate(subject, body)

    # c) Push the AI-generated draft back to the user's Gmail Drafts folder.
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    pushed = await gmail.create_draft(
        user,
        to=sender,
        subject=reply_subject,
        body=draft["draft"],
        thread_id=msg.get("thread_id") or None,
        in_reply_to=msg.get("message_id_header") or None,
    )
    logger.info("ai.gmail_draft_pushed", message_id=message_id, draft_id=pushed["draft_id"])
    return {
        "source_message_id": message_id,
        "draft": draft["draft"],
        "model": draft["model"],
        "citations": draft["citations"],
        "requires_human_review": True,
        "gmail_draft_id": pushed["draft_id"],
        "gmail_message_id": pushed["message_id"],
        "gmail_thread_id": pushed["thread_id"],
    }
