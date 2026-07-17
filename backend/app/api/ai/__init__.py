"""AI API (Phase 5): triage classification + draft generation.

All endpoints require an authenticated staff user and a configured Anthropic key
(503 otherwise). Drafts are human-in-the-loop — never sent automatically.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIError, AINotConfiguredError
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.user import User
from app.schemas.ai import DraftRequest, DraftResult, EmailInput, TriageResult
from app.schemas.gmail import GmailDraftPushResult
from app.services.draft_service import DraftService, push_gmail_reply
from app.services.gmail_service import GmailApiError, GmailNotConnectedError, GmailService
from app.services.triage_service import TriageService

logger = get_logger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])

_NOT_CONFIGURED = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="AI is not configured on this server (set ANTHROPIC_API_KEY)",
)
_NOT_CONNECTED = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="Google account is not connected.",
)


def _require_ai() -> None:
    if not settings.ai_configured:
        raise _NOT_CONFIGURED


def _ai_error(exc: AIError) -> HTTPException:
    # Surface the normalized message (never a raw stack trace) so clients get a
    # clear reason instead of an opaque 502.
    logger.warning("ai.request_failed", error=str(exc))
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"AI request failed: {exc}",
    )


@router.get("/status", summary="Module status")
async def status_() -> dict:
    return {
        "module": "ai",
        "implemented": True,
        "phase": 5,
        "configured": settings.ai_configured,
        "model": settings.ai_model,
    }


@router.post("/triage", response_model=TriageResult, summary="Classify an email")
async def triage(
    payload: EmailInput,
    current_user: User = Depends(get_current_user),
) -> TriageResult:
    _require_ai()
    try:
        data = await TriageService().classify(payload.subject, payload.body)
    except AINotConfiguredError as exc:
        raise _NOT_CONFIGURED from exc
    except AIError as exc:
        raise _ai_error(exc) from exc
    return TriageResult(**data)


@router.post("/draft", response_model=DraftResult, summary="Generate a reply draft")
async def draft(
    payload: DraftRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DraftResult:
    _require_ai()
    try:
        data = await DraftService(session).generate(
            payload.subject, payload.body, use_context=payload.use_context
        )
    except AINotConfiguredError as exc:
        raise _NOT_CONFIGURED from exc
    except AIError as exc:
        raise _ai_error(exc) from exc
    return DraftResult(**data)


async def _gmail_email(session: AsyncSession, user: User, message_id: str) -> tuple[str, str]:
    """Fetch a Gmail message and return (subject, body-ish text)."""
    try:
        msg = await GmailService(session).get_message(user, message_id)
    except GmailNotConnectedError as exc:
        raise _NOT_CONNECTED from exc
    # Prefer the full body; fall back to the snippet if the message has no
    # extractable textual part.
    return msg.get("subject", ""), (msg.get("body") or msg.get("snippet", ""))


@router.post(
    "/triage/gmail/{message_id}",
    response_model=TriageResult,
    summary="Triage a Gmail message by id",
)
async def triage_gmail(
    message_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TriageResult:
    _require_ai()
    subject, body = await _gmail_email(session, current_user, message_id)
    try:
        data = await TriageService().classify(subject, body)
    except AINotConfiguredError as exc:
        raise _NOT_CONFIGURED from exc
    except AIError as exc:
        raise _ai_error(exc) from exc
    return TriageResult(**data)


@router.post(
    "/draft/gmail/{message_id}",
    response_model=DraftResult,
    summary="Draft a reply to a Gmail message by id",
)
async def draft_gmail(
    message_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DraftResult:
    _require_ai()
    subject, body = await _gmail_email(session, current_user, message_id)
    try:
        data = await DraftService(session).generate(subject, body)
    except AINotConfiguredError as exc:
        raise _NOT_CONFIGURED from exc
    except AIError as exc:
        raise _ai_error(exc) from exc
    return DraftResult(**data)


@router.post(
    "/draft/gmail/{message_id}/push",
    response_model=GmailDraftPushResult,
    summary="Draft a reply with the RAG pipeline and push it to Gmail Drafts",
)
async def draft_gmail_push(
    message_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> GmailDraftPushResult:
    """End-to-end pipeline: fetch a patient email, generate a grounded reply
    draft, and create it in the mailbox's Drafts folder (gmail.compose).

    Human-in-the-loop: the draft is created but never sent — staff review and
    send it from Gmail.
    """
    _require_ai()
    try:
        data = await push_gmail_reply(session, current_user, message_id)
    except GmailNotConnectedError as exc:
        raise _NOT_CONNECTED from exc
    except AINotConfiguredError as exc:
        raise _NOT_CONFIGURED from exc
    except AIError as exc:
        raise _ai_error(exc) from exc
    except GmailApiError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gmail request failed: {exc}",
        ) from exc
    return GmailDraftPushResult(**data)
