"""Workflow intelligence API (Phase 6): run the triage → safety → retrieve →
draft pipeline on a Gmail message and persist a pending review."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIError, AINotConfiguredError
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.user import User
from app.schemas.review import DraftReviewRead
from app.services.gmail_service import GmailApiError, GmailNotConnectedError
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflows"])
logger = get_logger(__name__)

_NOT_CONFIGURED = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="AI is not configured on this server (set ANTHROPIC_API_KEY)",
)
_NOT_CONNECTED = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="Google account is not connected.",
)


@router.get("/status", summary="Module status")
async def status_() -> dict:
    return {"module": "workflows", "implemented": True, "phase": 6}


@router.post(
    "/pull",
    summary="Pull recent inbox mail and triage each new message → pending reviews",
)
async def pull_gmail(
    max_results: int = 12,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """One-click ingest: list recent Primary-inbox messages, skip any already in
    the review queue, and run the triage → draft pipeline on the rest. Returns a
    summary of how many reviews were created/skipped/failed."""
    if not settings.ai_configured:
        raise _NOT_CONFIGURED
    try:
        return await WorkflowService(session).pull_gmail(
            current_user, max_results=max_results
        )
    except GmailNotConnectedError as exc:
        raise _NOT_CONNECTED from exc
    except AINotConfiguredError as exc:
        raise _NOT_CONFIGURED from exc
    except GmailApiError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Gmail request failed: {exc}"
        ) from exc


@router.post(
    "/gmail/{message_id}",
    response_model=DraftReviewRead,
    summary="Run the workflow pipeline on a Gmail message → pending review",
)
async def run_gmail(
    message_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DraftReviewRead:
    if not settings.ai_configured:
        raise _NOT_CONFIGURED
    try:
        review = await WorkflowService(session).run_gmail(current_user, message_id)
    except GmailNotConnectedError as exc:
        raise _NOT_CONNECTED from exc
    except AINotConfiguredError as exc:
        raise _NOT_CONFIGURED from exc
    except AIError as exc:
        logger.warning("workflow.ai_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI request failed: {exc}"
        ) from exc
    except GmailApiError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Gmail request failed: {exc}"
        ) from exc
    return DraftReviewRead.model_validate(review)
