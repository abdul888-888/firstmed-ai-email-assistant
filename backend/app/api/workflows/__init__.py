"""Workflow intelligence API (Phase 6): run the triage → safety → retrieve →
draft pipeline on a Gmail message and persist a pending review."""

from __future__ import annotations

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIError, AINotConfiguredError
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.user import User
from app.repositories.draft_review import DuplicateReviewError
from app.schemas.review import DraftReviewRead
from app.services.gmail_service import GmailApiError, GmailNotConnectedError
from app.services.workflow_service import WorkflowService
from app.tasks.workflow_tasks import DEFAULT_PULL_QUERY, pull_gmail_task
from app.workers.celery_app import celery_app

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
    "/pull-async",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue a background Gmail pull (Celery) — returns immediately with a task id",
)
async def pull_gmail_async(
    max_results: int = 12,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Non-blocking variant of ``POST /pull``: enqueues the same triage
    pipeline on a Celery worker instead of running it inline the HTTP request,
    so it can't hit a request timeout and per-message Gmail/AI errors can be
    retried. Requires a Celery worker to be running
    (``celery -A app.workers.celery_app worker``) — otherwise the task sits
    queued until one picks it up. Poll ``GET /pull-async/{task_id}`` for the
    result. The existing synchronous ``POST /pull`` is unchanged and still
    works with no worker running.
    """
    if not settings.ai_configured:
        raise _NOT_CONFIGURED
    task = pull_gmail_task.delay(str(current_user.id), max_results, DEFAULT_PULL_QUERY)
    return {"task_id": task.id, "status": "queued"}


@router.get(
    "/pull-async/{task_id}",
    summary="Check the status/result of a background Gmail pull",
)
async def pull_gmail_async_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    result = AsyncResult(task_id, app=celery_app)
    body: dict = {"task_id": task_id, "state": result.state}
    if result.state == "SUCCESS":
        body["result"] = result.result
    elif result.state == "FAILURE":
        body["error"] = str(result.result)
    return body


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
    except DuplicateReviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This message has already been triaged (a review already exists).",
        ) from exc
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
