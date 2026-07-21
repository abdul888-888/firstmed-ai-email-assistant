"""Workflow intelligence engine (Phase 6).

Orchestrates the explicit, ordered pipeline over one inbound Gmail message:

    1. triage        (Claude, structured)   -> intent / urgency / department / confidence
    2. safety check  (pure rules)           -> ADMIN_DIRECT_REPLY | NEEDS_PHYSICIAN_REVIEW
    3. retrieve      (RAG over SOP index)    -> grounding context + citations
    4. draft         (Claude, grounded)      -> reply body (escalated items still get a
                                                safe, clinician-deferring draft)

The engine then persists a ``DraftReview`` with ``status=pending`` and — per the
Phase 6 decision — writes **nothing to Gmail**. A Gmail draft is created only when
a human approves (:meth:`approve`), which still never *sends*.

AI-backed dependencies are injectable so tests use fakes / mock transports and
never hit the network.
"""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIClient
from app.core.logging import get_logger
from app.models.draft_review import DraftReview
from app.models.user import User
from app.repositories.draft_review import DraftReviewRepository
from app.schemas.review import ReviewStatus
from app.services.draft_service import DraftService
from app.services.gmail_service import GmailService
from app.services.safety import classify_review
from app.services.triage_service import TriageService

logger = get_logger(__name__)


class WorkflowService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        ai: AIClient | None = None,
        gmail_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.session = session
        self.repo = DraftReviewRepository(session)
        self.triage = TriageService(ai)
        self.draft = DraftService(session, ai)
        self.gmail = GmailService(session, client=gmail_client)

    async def pull_gmail(
        self,
        user: User,
        *,
        max_results: int = 12,
        query: str = "in:inbox -category:promotions -category:social -category:updates -category:forums",
    ) -> dict[str, int]:
        """List recent inbox messages and triage every one not seen before.

        Idempotent: messages that already have a review (any status) are skipped,
        so repeated pulls never duplicate cards. Per-message AI/Gmail failures are
        logged and skipped rather than aborting the whole pull. Defaults to the
        inbox minus the noise categories (promotions/social/updates/forums); those
        negative filters are harmless no-ops on accounts without tabbed categories,
        so we still get the real inbox rather than an empty ``category:primary``.

        Returns a summary: ``{"created", "skipped", "failed", "scanned"}``.
        """
        listing = await self.gmail.list_messages(
            user, max_results=max_results, query=query
        )
        messages = listing.get("messages", []) or []
        seen = await self.repo.existing_message_ids(user.id)

        created = skipped = failed = 0
        for m in messages:
            mid = m.get("id")
            if not mid or mid in seen:
                skipped += 1
                continue
            try:
                await self.run_gmail(user, mid)
                seen.add(mid)
                created += 1
            except Exception as exc:  # noqa: BLE001 — one bad email must not abort the batch
                failed += 1
                await self.session.rollback()
                logger.warning(
                    "workflow.pull_item_failed",
                    message_id=mid,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
        summary = {
            "created": created,
            "skipped": skipped,
            "failed": failed,
            "scanned": len(messages),
        }
        logger.info("workflow.pull_complete", **summary)
        return summary

    async def run_gmail(self, user: User, message_id: str) -> DraftReview:
        """Run the pipeline on a Gmail message and persist a pending review.

        Propagates domain errors for the API to translate: ``GmailNotConnectedError``
        / ``GmailApiError`` and ``AIError`` / ``AINotConfiguredError``.
        """
        # Step 0/1 input — fetch the incoming email (full body, snippet fallback).
        msg = await self.gmail.get_message(user, message_id)
        subject = msg.get("subject", "")
        body = msg.get("body") or msg.get("snippet", "")

        # Step 1 — triage.
        triage = await self.triage.classify(subject, body)

        # Step 2 — safety gate (pure).
        classification, reason = classify_review(triage)

        # For irrelevant emails, skip draft generation and mark as irrelevant.
        if classification.value == "IRRELEVANT":
            review = await self.repo.create(
                user_id=user.id,
                gmail_message_id=msg.get("id", message_id),
                gmail_thread_id=msg.get("thread_id", ""),
                message_id_header=msg.get("message_id_header", ""),
                sender=msg.get("from", ""),
                subject=subject,
                intent=str(triage.get("intent", "")),
                urgency=str(triage.get("urgency", "")),
                department=str(triage.get("department", "")),
                classification=classification.value,
                confidence=float(triage.get("confidence", 0.0)),
                summary=str(triage.get("summary", "")),
                reason=reason,
                draft_body="",
                citations=[],
                model="",
                status=ReviewStatus.irrelevant.value,
            )
            logger.info(
                "workflow.review_irrelevant",
                review_id=str(review.id),
            )
            return review

        # For specialist escalations, mark as awaiting_specialist_input.
        status = ReviewStatus.pending.value
        if classification.value == "NEEDS_PHYSICIAN_REVIEW":
            status = ReviewStatus.awaiting_specialist_input.value

        # Steps 3+4 — retrieve + draft (DraftService does RAG then generation).
        draft = await self.draft.generate(subject, body)

        review = await self.repo.create(
            user_id=user.id,
            gmail_message_id=msg.get("id", message_id),
            gmail_thread_id=msg.get("thread_id", ""),
            message_id_header=msg.get("message_id_header", ""),
            sender=msg.get("from", ""),
            subject=subject,
            intent=str(triage.get("intent", "")),
            urgency=str(triage.get("urgency", "")),
            department=str(triage.get("department", "")),
            classification=classification.value,
            confidence=float(triage.get("confidence", 0.0)),
            summary=str(triage.get("summary", "")),
            reason=reason,
            draft_body=draft["draft"],
            citations=draft["citations"],
            model=draft["model"],
            status=status,
        )
        logger.info(
            "workflow.review_created",
            review_id=str(review.id),
            classification=classification.value,
            confidence=review.confidence,
        )
        return review

    async def approve(self, user: User, review: DraftReview) -> DraftReview:
        """Human-in-the-loop gate: push the vetted draft to Gmail Drafts (never
        sends), then mark the review approved. Assumes the caller has verified the
        review is pending and owned by ``user``.
        """
        subject = review.subject or ""
        reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        pushed = await self.gmail.create_draft(
            user,
            to=review.sender,
            subject=reply_subject,
            body=review.draft_body,
            thread_id=review.gmail_thread_id or None,
            in_reply_to=review.message_id_header or None,
        )
        updated = await self.repo.mark_approved(
            review, gmail_draft_id=pushed["draft_id"], reviewed_by=user.id
        )
        logger.info(
            "workflow.review_approved",
            review_id=str(review.id),
            gmail_draft_id=pushed["draft_id"],
        )
        return updated

    async def reject(self, user: User, review: DraftReview, reason: str) -> DraftReview:
        """Reject a pending review with a reason. No Gmail interaction."""
        updated = await self.repo.mark_rejected(review, reviewed_by=user.id, note=reason)
        logger.info("workflow.review_rejected", review_id=str(review.id))
        return updated

    async def send(self, user: User, review: DraftReview) -> DraftReview:
        """Send the approved review's Gmail draft (outward-facing — delivers mail).

        Caller must have verified the review is ``approved`` and owned by ``user``.
        """
        result = await self.gmail.send_draft(user, review.gmail_draft_id or "")
        updated = await self.repo.mark_sent(review, sent_message_id=result["message_id"])
        logger.info(
            "workflow.review_sent",
            review_id=str(review.id),
            sent_message_id=result["message_id"],
        )
        return updated

    async def receive_specialist_input(
        self, user: User, review: DraftReview, specialist_input: str, should_revise: bool = True
    ) -> DraftReview:
        """Record specialist input for an escalated review.

        If should_revise is True, regenerate the draft incorporating specialist guidance.
        """
        # Record the specialist input.
        updated = await self.repo.add_specialist_input(
            review, specialist_input=specialist_input, specialist_id=user.id
        )
        logger.info(
            "workflow.specialist_input_received",
            review_id=str(review.id),
            specialist_id=str(user.id),
        )

        # If requested, regenerate the draft with specialist guidance.
        if should_revise and updated.subject and updated.draft_body:
            prompt = (
                f"Original patient email: {updated.subject}\n\n"
                f"Specialist guidance:\n{specialist_input}\n\n"
                f"Revise the draft reply to incorporate this specialist guidance:\n"
                f"{updated.draft_body}"
            )
            revised = await self.draft.generate(updated.subject, updated.draft_body)
            updated = await self.repo.update_body(updated, draft_body=revised["draft"])
            logger.info(
                "workflow.draft_revised_with_specialist_input",
                review_id=str(review.id),
            )

        return updated
