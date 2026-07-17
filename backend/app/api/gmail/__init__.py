"""Gmail integration API (Phase 2): read access to the shared clinical inbox."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIError, AINotConfiguredError
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.user import User
from app.schemas.gmail import (
    GmailConnection,
    GmailDraftList,
    GmailDraftPushResult,
    GmailMessage,
    GmailMessageList,
)
from app.services.draft_service import push_gmail_reply
from app.services.gmail_service import GmailApiError, GmailNotConnectedError, GmailService

router = APIRouter(prefix="/gmail", tags=["gmail"])
logger = get_logger(__name__)

_NOT_CONNECTED = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="Google account is not connected. Sign in with Google to grant Gmail access.",
)
_NOT_CONFIGURED = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="AI is not configured on this server (set ANTHROPIC_API_KEY)",
)


@router.get("/status", summary="Module status")
async def status_() -> dict:
    return {"module": "gmail", "implemented": True, "phase": 2}


@router.get(
    "/connection",
    response_model=GmailConnection,
    summary="Whether the current user has linked Gmail access",
)
async def connection(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> GmailConnection:
    return await GmailService(session).get_connection(current_user)


@router.get(
    "/messages",
    response_model=GmailMessageList,
    summary="List messages in the shared inbox",
)
async def list_messages(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    max_results: int = Query(default=25, ge=1, le=100),
    q: str | None = Query(default=None, description="Gmail search query"),
) -> GmailMessageList:
    try:
        data = await GmailService(session).list_messages(
            current_user, max_results=max_results, query=q
        )
    except GmailNotConnectedError as exc:
        raise _NOT_CONNECTED from exc
    return GmailMessageList(**data)


@router.get(
    "/drafts",
    response_model=GmailDraftList,
    summary="List drafts in the shared inbox",
)
async def list_drafts(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    max_results: int = Query(default=25, ge=1, le=100),
) -> GmailDraftList:
    try:
        data = await GmailService(session).list_drafts(current_user, max_results=max_results)
    except GmailNotConnectedError as exc:
        raise _NOT_CONNECTED from exc
    return GmailDraftList(**data)


@router.get(
    "/messages/{message_id}",
    response_model=GmailMessage,
    summary="Fetch a single message (headers, snippet, and full body)",
)
async def get_message(
    message_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> GmailMessage:
    try:
        data = await GmailService(session).get_message(current_user, message_id)
    except GmailNotConnectedError as exc:
        raise _NOT_CONNECTED from exc
    return GmailMessage.model_validate(data)


@router.post(
    "/messages/{message_id}/draft",
    response_model=GmailDraftPushResult,
    summary="Triage + draft a reply and push it to Gmail Drafts",
)
async def create_draft_reply(
    message_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> GmailDraftPushResult:
    """Alias of ``POST /ai/draft/gmail/{message_id}/push`` on the Gmail router:
    fetch the message, generate a grounded reply, and create it in Drafts.

    Human-in-the-loop: the draft is created but never sent.
    """
    if not settings.ai_configured:
        raise _NOT_CONFIGURED
    try:
        data = await push_gmail_reply(session, current_user, message_id)
    except GmailNotConnectedError as exc:
        raise _NOT_CONNECTED from exc
    except AINotConfiguredError as exc:
        raise _NOT_CONFIGURED from exc
    except AIError as exc:
        logger.warning("gmail.draft_ai_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI request failed: {exc}",
        ) from exc
    except GmailApiError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gmail request failed: {exc}",
        ) from exc
    return GmailDraftPushResult(**data)
