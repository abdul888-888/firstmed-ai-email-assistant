"""Workflow intelligence engine (Phase 6).

Orchestrates the explicit, ordered pipeline over one inbound email message:

    1. triage        (Claude, structured)   -> intent / urgency / department / confidence
    2. safety check  (pure rules)           -> ADMIN_DIRECT_REPLY | NEEDS_PHYSICIAN_REVIEW
    3. retrieve      (RAG over SOP index)    -> grounding context + citations
    4. draft         (Claude, grounded)      -> reply body (escalated items still get a
                                                safe, clinician-deferring draft)

The engine then persists a ``DraftReview`` with ``status=pending`` and — per the
Phase 6 decision — writes **nothing to the email provider**. A draft is created
only when a human approves (:meth:`approve`), which still never *sends*.

AI-backed dependencies are injectable so tests use fakes / mock transports and
never hit the network. The email provider is also injectable so tests can use
a FakeEmailProvider without connecting to Gmail, Outlook, or IMAP servers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIClient
from app.core.email import BaseEmailProvider, get_email_provider
from app.core.logging import get_logger
from app.models.draft_review import DraftReview
from app.models.user import User
from app.repositories.connected_account import ConnectedAccountRepository
from app.repositories.draft_review import (
    DraftReviewRepository,
    DuplicateReviewError,
)
from app.schemas.email import NormalizedEmail
from app.schemas.review import ReviewClassification, ReviewStatus
from app.services.draft_service import DraftService
from app.services.safety import classify_review
from app.services.triage_service import TriageService

if TYPE_CHECKING:
    from app.models.connected_account import ConnectedAccount

logger = get_logger(__name__)


class WorkflowService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        ai: AIClient | None = None,
        email_provider: BaseEmailProvider | None = None,
    ) -> None:
        """Initialize the workflow service.

        Args:
            session: AsyncSession for database access.
            ai: Optional AIClient for triage/draft generation. If None, uses defaults.
            email_provider: Optional BaseEmailProvider for email operations. If None,
                providers are resolved lazily from ConnectedAccount rows via the factory.
        """
        self.session = session
        self.repo = DraftReviewRepository(session)
        self.account_repo = ConnectedAccountRepository(session)
        self.triage = TriageService(ai)
        self.draft = DraftService(session, ai)
        self._email_provider = email_provider

    async def _provider(
        self, account: ConnectedAccount | None
    ) -> BaseEmailProvider:
        """Lazy-resolve the email provider for an account.

        If the service was initialized with an injected provider, use that
        (typically for testing with a FakeEmailProvider). Otherwise, resolve
        the provider from the account's provider_type via the factory.
        """
        if self._email_provider is not None:
            return self._email_provider
        if account is None:
            from app.core.email import EmailProviderNotConnectedError

            raise EmailProviderNotConnectedError("No email account connected")
        return get_email_provider(account, self.session)

    async def pull_messages(
        self,
        user: User,
        account: ConnectedAccount,
        *,
        max_results: int = 12,
        query: str | None = None,
    ) -> dict[str, int]:
        """List recent messages from a connected account and triage every one not seen before.

        Provider-agnostic replacement for ``pull_gmail``. Works with any provider
        (Gmail, Outlook, IMAP/SMTP).

        Idempotent: messages that already have a review (any status) are skipped,
        so repeated pulls never duplicate cards. The ``existing_message_ids``
        pre-check handles the common case; a DB-level unique constraint on
        ``(user_id, provider_message_id)`` is the race-safe backstop for two
        concurrent pulls.

        Returns a summary: ``{"created", "skipped", "failed", "scanned"}``.
        """
        provider = await self._provider(account)
        messages, new_cursor = await provider.fetch_messages(
            account.history_id,
            max_results=max_results,
            query=query,
        )

        # Persist the new cursor for next time.
        if new_cursor is not None:
            await self.account_repo.update_history_id(account, history_id=new_cursor)

        seen = await self.repo.existing_message_ids(user.id)

        created = skipped = failed = 0
        for msg in messages:
            mid = msg.external_message_id
            if mid in seen:
                skipped += 1
                continue
            try:
                await self.run_message(user, account, msg)
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

    async def run_message(
        self, user: User, account: ConnectedAccount, message: NormalizedEmail
    ) -> DraftReview:
        """Run the pipeline on a normalized email message and persist a pending review.

        Provider-agnostic replacement for ``run_gmail``. Works with any provider.
        """
        subject = message.subject
        body = message.body_text or message.raw_headers.get("snippet", "")

        # Step 1 — triage. Skipped entirely for messages already marked as noise
        # by the provider's own labels (spam, promotions, etc.). The safety gate
        # below still runs its deterministic checks, so genuine emergencies
        # can't be silently dropped.
        if message.is_noise:
            triage = {
                "intent": "irrelevant",
                "urgency": "low",
                "department": "front_office",
                "summary": "Skipped — provider labels mark this as noise (spam/promotions/sent/draft).",
                "confidence": 1.0,
            }
        else:
            triage = await self.triage.classify(subject, body)

        # Step 2 — safety gate (pure, deterministic).
        decision = classify_review(triage, text=f"{subject}\n{body}")
        classification, reason, department = (
            decision.classification,
            decision.reason,
            decision.department,
        )

        # Steps 3+4 — retrieve + draft, but only for safe outcomes.
        draft_body = ""
        citations: list[dict] = []
        model = ""

        if classification is ReviewClassification.IRRELEVANT:
            status = ReviewStatus.irrelevant.value
        elif classification is ReviewClassification.NEEDS_PHYSICIAN_REVIEW:
            status = ReviewStatus.awaiting_specialist_input.value
        elif classification is ReviewClassification.ROUTE_TO_STAFF:
            status = ReviewStatus.needs_manual_handling.value
        else:  # ADMIN_DIRECT_REPLY
            draft = await self.draft.generate(subject, body, abstain_if_ungrounded=True)
            if not draft.get("grounded", True):
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
            provider_message_id=message.external_message_id,
            provider_thread_id=message.external_thread_id or "",
            message_id_header=message.message_id_header or "",
            sender=message.sender,
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

    async def approve(self, user: User, account: ConnectedAccount, review: DraftReview) -> DraftReview:
        """Human-in-the-loop gate: push the vetted draft to the email provider (never sends).

        Uses the email provider to create a draft, then marks the review approved.
        Claims the row atomically (pending/specialist_input_received -> approved)
        BEFORE calling the provider, so if two requests race, only the winner reaches
        the provider API. On failure after the claim, the status is reverted.
        """
        from app.repositories.draft_review import StaleReviewStatusError

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
            provider = await self._provider(account)
            draft_id = await provider.create_draft(
                to=claimed.sender,
                subject=reply_subject,
                body=claimed.draft_body,
                thread_id=claimed.provider_thread_id or None,
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
            claimed, provider_draft_id=draft_id, reviewed_by=user.id
        )
        logger.info(
            "workflow.review_approved",
            review_id=str(review.id),
            provider_draft_id=draft_id,
        )
        return updated

    async def reject(self, user: User, review: DraftReview, reason: str) -> DraftReview:
        """Reject a pending review with a reason. No provider interaction.

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

    async def send(self, user: User, account: ConnectedAccount, review: DraftReview) -> DraftReview:
        """Send the approved review's draft (outward-facing — delivers mail).

        Uses the email provider to send the draft. Claims the row atomically
        (approved -> sent) BEFORE calling the provider, so a double-send race
        can't both reach the provider. On failure after the claim, the status
        is reverted to ``approved`` so the review can be retried.
        """
        from app.repositories.draft_review import StaleReviewStatusError

        claimed = await self.repo.claim_status(
            review.id,
            from_statuses=[ReviewStatus.approved.value],
            to_status=ReviewStatus.sent.value,
        )
        try:
            provider = await self._provider(account)
            sent_message_id = await provider.send_draft(claimed.provider_draft_id or "")
        except Exception:
            await self.repo.claim_status(
                claimed.id,
                from_statuses=[ReviewStatus.sent.value],
                to_status=ReviewStatus.approved.value,
            )
            raise
        updated = await self.repo.mark_sent(claimed, sent_message_id=sent_message_id)
        logger.info(
            "workflow.review_sent",
            review_id=str(review.id),
            sent_message_id=sent_message_id,
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
        # guidance. Escalated reviews start with an EMPTY draft, so this is
        # the first time a draft is written — it must be built FROM the
        # specialist input, not the generic pipeline.
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
