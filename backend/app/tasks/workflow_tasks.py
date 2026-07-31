"""Celery tasks for the Gmail pull/triage/draft pipeline.

Moves ``WorkflowService.pull_gmail`` — the per-message loop that previously ran
synchronously inside the ``POST /workflows/pull`` request handler — onto a
Celery worker. This closes two scalability gaps from the original audit:
nothing pulls mail automatically (no periodic schedule existed), and the
in-request loop had no timeout headroom or retry on transient Gmail/AI
failures.

The existing synchronous ``/workflows/pull`` endpoint is UNCHANGED and still
works with no worker running — this module only adds new, additive capability
(an on-demand async trigger + status endpoint, and a Beat-scheduled auto-pull
for every connected mailbox). See ``app/api/workflows/__init__.py``.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.client import AIError, AINotConfiguredError
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.repositories.google_credential import GoogleCredentialRepository
from app.repositories.user import UserRepository
from app.services.gmail_service import GmailApiError, GmailNotConnectedError
from app.services.workflow_service import WorkflowService
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

DEFAULT_PULL_QUERY = (
    "in:inbox -category:promotions -category:social -category:updates -category:forums"
)

# Errors worth retrying (transient I/O at the Gmail/Anthropic API boundary).
# Config/state errors (no Gmail link, no API key, deleted user) are permanent
# for this invocation — retrying them just delays the failure being visible.
_RETRYABLE_ERRORS = (GmailApiError, AIError)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine to completion inside a synchronous Celery task.

    Celery's prefork workers execute tasks as plain sync functions; the app's
    services (SQLAlchemy AsyncSession, httpx.AsyncClient) are async-only. Each
    task invocation gets its own fresh event loop via ``asyncio.run`` rather
    than sharing one across tasks/threads. The database engine is disposed at
    the end of the loop so connections are never leaked or reused across loops.
    """
    async def _runner() -> Any:
        from app.core.database import engine
        try:
            return await coro
        finally:
            await engine.dispose()

    return asyncio.run(_runner())


SessionFactory = Callable[[], "AsyncSession"]


async def _pull_gmail_async(
    user_id: str,
    max_results: int,
    query: str,
    *,
    session_factory: async_sessionmaker[AsyncSession] | SessionFactory = AsyncSessionLocal,
) -> dict:
    """The task's actual logic, independent of Celery/asyncio wrapping.

    ``session_factory`` defaults to the app's real session factory (bound to
    the configured production/dev DB) but is injectable so tests can pass the
    isolated per-test session factory instead of hitting a real database.
    """
    async with session_factory() as session:
        user = await UserRepository(session).get_by_id(uuid.UUID(user_id))
        if user is None:
            raise ValueError(f"User {user_id} not found")
        return await WorkflowService(session).pull_gmail(
            user, max_results=max_results, query=query
        )


async def _list_connected_user_ids_async(
    *, session_factory: async_sessionmaker[AsyncSession] | SessionFactory = AsyncSessionLocal
) -> list[str]:
    async with session_factory() as session:
        ids = await GoogleCredentialRepository(session).list_connected_user_ids()
        return [str(i) for i in ids]


@celery_app.task(
    name="workflow.pull_gmail",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def pull_gmail_task(
    self, user_id: str, max_results: int = 12, query: str = DEFAULT_PULL_QUERY
) -> dict:
    """Background task: list a user's recent inbox mail and triage each new
    message (same pipeline the synchronous endpoint runs inline). Per-message
    failures are already caught inside ``WorkflowService.pull_gmail`` and
    counted rather than raised; only a top-level failure (Gmail not linked, AI
    not configured, a transient Gmail/AI API error before the loop starts)
    reaches this task boundary.
    """
    try:
        return _run_async(_pull_gmail_async(user_id, max_results, query))
    except _RETRYABLE_ERRORS as exc:
        logger.warning(
            "workflow.pull_task_retrying",
            user_id=user_id,
            error=str(exc),
            error_type=type(exc).__name__,
            attempt=self.request.retries,
        )
        raise self.retry(exc=exc) from exc
    except (GmailNotConnectedError, AINotConfiguredError, ValueError) as exc:
        # Permanent for this invocation — surface immediately, no retry.
        logger.warning(
            "workflow.pull_task_permanent_failure",
            user_id=user_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise


@celery_app.task(name="workflow.pull_all_connected")
def pull_all_connected_task(max_results: int = 12) -> dict:
    """Beat-scheduled: fan out a pull to every mailbox with a linked Google
    account, so new mail is triaged automatically without a human clicking
    Sync. Each user's pull is its own retryable, independently-failing task —
    one user's Gmail/AI error never blocks or fails another's.
    """
    user_ids = _run_async(_list_connected_user_ids_async())
    for uid in user_ids:
        pull_gmail_task.delay(uid, max_results, DEFAULT_PULL_QUERY)
    logger.info("workflow.auto_pull_fanned_out", user_count=len(user_ids))
    return {"enqueued": len(user_ids)}
