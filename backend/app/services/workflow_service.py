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
from app.repositories.draft_review import (
    DraftReviewRepository,
    DuplicateReviewError,
    StaleReviewStatusError,
)
from app.schemas.review import ReviewClassification, ReviewStatus
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
        so repeated pulls never duplicate cards. The ``existing_message_ids``
        pre-check handles the common case; a DB-level unique constraint on
        ``(user_id, gmail_message_id)`` is the race-safe backstop for two
        concurrent pulls (or a pull racing the direct single-message endpoint) —
        a duplicate insert there is caught as :class:`DuplicateReviewError` and
        counted as skipped, not failed. Per-message AI/Gmail failures are logged
        and skipped rather than aborting the whole pull. Defaults to the inbox
        minus the noise categories (promotions/social/updates/forums); those
        negative filters are harmless no-ops on accounts without tabbed categories,
        so we still get the real inbox rather than an empty ``category:primary``.

        Uses ``GmailService.list_new_messages`` — incremental (Gmail history)
        sync once a cursor is bootstrapped, falling back to this bounded
        search only on the first pull or once history has expired. ``query``
        only applies to that fallback path (history sync has no query concept
        — it returns everything new since last time, full stop).

        Returns a summary: ``{"created", "skipped", "failed", "scanned"}``.
        """
        listing = await self.gmail.list_new_messages(
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
            except DuplicateReviewError:
                skipped += 1
                await self.session.rollback()
                logger.info("workflow.pull_item_duplicate", message_id=mid)
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

        # Step 1 — triage. Skipped entirely (no LLM call) for messages Gmail's
        # own labels already mark as noise — spam, promotions/social/forums/
        # updates categories, or our own sent/draft copies (see the metadata-
        # first fetch in GmailService.get_message). The safety gate below still
        # runs its deterministic keyword checks against whatever text remains
        # (the snippet), so a genuine emergency can never be silently dropped
        # by this shortcut — only the LLM classification call is skipped.
        if msg.get("is_noise"):
            triage = {
                "intent": "irrelevant",
                "urgency": "low",
                "department": "front_office",
                "summary": "Skipped — Gmail labels mark this as spam/promotions/social/sent/draft.",
                "confidence": 1.0,
            }
        else:
            triage = await self.triage.classify(subject, body)

        # Step 2 — safety gate (pure, deterministic). The raw text is passed so
        # keyword gates (emergency / legal / billing dispute / domain-specific
        # exclusions) can override a mis-triaged intent. The decision also
        # carries the department (possibly overridden from the LLM's own pick,
        # e.g. tagged "laboratory"/"gastroenterology"/"physiotherapy") so the
        # persisted review routes to the right team, not just a generic bucket.
        decision = classify_review(triage, text=f"{subject}\n{body}")
        classification, reason, department = (
            decision.classification,
            decision.reason,
            decision.department,
        )

        # Steps 3+4 — retrieve + draft, but ONLY for administrative emails cleared
        # by the safety gate. Every other outcome is a hard exclusion: we persist a
        # review with an EMPTY draft and route it to a human. Draft generation is
        # never even reached for appointments, clinical questions, complaints, etc.
        draft_body = ""
        citations: list[dict] = []
        model = ""

        if classification is ReviewClassification.IRRELEVANT:
            status = ReviewStatus.irrelevant.value
        elif classification is ReviewClassification.NEEDS_PHYSICIAN_REVIEW:
            status = ReviewStatus.awaiting_specialist_input.value
        elif classification is ReviewClassification.ROUTE_TO_STAFF:
            status = ReviewStatus.needs_manual_handling.value
        else:  # ADMIN_DIRECT_REPLY — the only draft-eligible outcome.
            draft = await self.draft.generate(subject, body, abstain_if_ungrounded=True)
            if not draft.get("grounded", True):
                # Knowledge-base miss: abstain rather than fabricate an answer.
                status = ReviewStatus.needs_manual_handling.value
                reason = f"{reason} No knowledge-base match — manual handling required."
                logger.info(
                    "workflow.knowledge_gap",
                    subject=subject,
                    intent=str(triage.get("intent", "")),
                )
            else:
                status = ReviewStatus.pending.value
                draft_body = draft["draft"]
                citations = draft["citations"]
                model = draft["model"]

        review = await self.repo.create(
            user_id=user.id,
            gmail_message_id=msg.get("id", message_id),
            gmail_thread_id=msg.get("thread_id", ""),
            message_id_header=msg.get("message_id_header", ""),
            sender=msg.get("from", ""),
            subject=subject,
            intent=str(triage.get("intent", "")),
            urgency=str(triage.get("urgency", "")),
            department=department,
            classification=classification.value,
            confidence=float(triage.get("confidence", 0.0)),
            summary=str(triage.get("summary", "")),
            reason=reason,
            draft_body=draft_body,
            citations=citations,
            model=model,
            status=status,
        )
        logger.info(
            "workflow.review_created",
            review_id=str(review.id),
            classification=classification.value,
            status=status,
            confidence=review.confidence,
        )
        return review

    async def approve(self, user: User, review: DraftReview) -> DraftReview:
        """Human-in-the-loop gate: push the vetted draft to Gmail Drafts (never
        sends), then mark the review approved.

        Claims the row atomically (pending/specialist_input_received ->
        approved) BEFORE calling Gmail, so if two requests race (two staff, or a
        double-click), only the winner ever reaches the Gmail API — the loser
        raises :class:`StaleReviewStatusError` immediately. On a Gmail failure
        after the claim, the status is reverted so the review can be retried.
        """
        original_status = review.status
        claimed = await self.repo.claim_status(
            review.id,
            from_statuses=[
                ReviewStatus.pending.value,
                ReviewStatus.specialist_input_received.value,
            ],
            to_status=ReviewStatus.approved.value,
        )
        subject = claimed.subject or ""
        reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        try:
            pushed = await self.gmail.create_draft(
                user,
                to=claimed.sender,
                subject=reply_subject,
                body=claimed.draft_body,
                thread_id=claimed.gmail_thread_id or None,
                in_reply_to=claimed.message_id_header or None,
            )
        except Exception:
            await self.repo.claim_status(
                claimed.id,
                from_statuses=[ReviewStatus.approved.value],
                to_status=original_status,
            )
            raise
        updated = await self.repo.mark_approved(
            claimed, gmail_draft_id=pushed["draft_id"], reviewed_by=user.id
        )
        logger.info(
            "workflow.review_approved",
            review_id=str(review.id),
            gmail_draft_id=pushed["draft_id"],
        )
        return updated

    async def reject(self, user: User, review: DraftReview, reason: str) -> DraftReview:
        """Reject a pending review with a reason. No Gmail interaction.

        Claims the row atomically so a reject can't race an approve/send on the
        same review.
        """
        claimed = await self.repo.claim_status(
            review.id,
            from_statuses=[
                ReviewStatus.pending.value,
                ReviewStatus.specialist_input_received.value,
            ],
            to_status=ReviewStatus.rejected.value,
        )
        updated = await self.repo.mark_rejected(claimed, reviewed_by=user.id, note=reason)
        logger.info("workflow.review_rejected", review_id=str(review.id))
        return updated

    async def send(self, user: User, review: DraftReview) -> DraftReview:
        """Send the approved review's Gmail draft (outward-facing — delivers mail).

        Claims the row atomically (approved -> sent) BEFORE calling Gmail, so a
        double-send race (two requests both passing the pre-check) can never
        both reach ``gmail.send_draft`` — the second raises
        :class:`StaleReviewStatusError`. On a Gmail failure after the claim, the
        status is reverted to ``approved`` so the review can be retried.
        """
        claimed = await self.repo.claim_status(
            review.id,
            from_statuses=[ReviewStatus.approved.value],
            to_status=ReviewStatus.sent.value,
        )
        try:
            result = await self.gmail.send_draft(user, claimed.gmail_draft_id or "")
        except Exception:
            await self.repo.claim_status(
                claimed.id,
                from_statuses=[ReviewStatus.sent.value],
                to_status=ReviewStatus.approved.value,
            )
            raise
        updated = await self.repo.mark_sent(claimed, sent_message_id=result["message_id"])
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

        # If requested, (re)generate the draft grounded on the specialist's
        # guidance. Escalated reviews start with an EMPTY draft (no AI text is
        # produced for clinical email pre-review), so this is the first time a
        # draft is written — it must be built FROM the specialist input, not the
        # generic pipeline. We pass the guidance as authoritative context.
        if should_revise and updated.subject:
            patient_context = updated.summary or updated.subject
            revised = await self.draft.generate(
                updated.subject,
                patient_context,
                extra_context=(
                    "SPECIALIST GUIDANCE (authoritative — base the reply on this):\n"
                    f"{specialist_input}"
                ),
            )
            updated = await self.repo.update_body(updated, draft_body=revised["draft"])
            logger.info(
                "workflow.draft_revised_with_specialist_input",
                review_id=str(review.id),
            )

        return updated
