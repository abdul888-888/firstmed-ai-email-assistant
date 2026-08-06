"""Celery tasks for the multi-provider email pull/triage/draft pipeline.

Moves ``WorkflowService.pull_messages`` — the per-message loop that previously
ran synchronously inside the ``POST /workflows/pull`` request handler — onto a
Celery worker. This closes two scalability gaps from the original audit:
nothing pulls mail automatically (no periodic schedule existed), and the
in-request loop had no timeout headroom or retry on transient provider/AI
failures.

The existing synchronous ``/workflows/pull`` endpoint is UNCHANGED and still
works with no worker running — this module only adds new, additive capability
(an on-demand async trigger + status endpoint, and a Beat-scheduled auto-pull
for every connected mailbox) across all provider types (Gmail, Outlook,
IMAP/SMTP).

See ``app/api/workflows/__init__.py``.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.client import AIError, AINotConfiguredError
from app.core.database import AsyncSessionLocal
from app.core.email import EmailProviderError, EmailProviderNotConnectedError
from app.core.logging import get_logger
from app.repositories.connected_account import ConnectedAccountRepository
from app.repositories.user import UserRepository
from app.services.workflow_service import WorkflowService
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

DEFAULT_PULL_QUERY = (
    "in:inbox -category:promotions -category:social -category:updates -category:forums"
)

# Errors worth retrying (transient I/O at the email provider/Anthropic API boundary).
# Config/state errors (no email account, no API key, deleted user) are permanent
# for this invocation — retrying them just delays the failure being visible.
_RETRYABLE_ERRORS = (EmailProviderError, AIError)


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


async def _pull_messages_async(
    user_id: str,
    account_id: str,
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

        account_repo = ConnectedAccountRepository(session)
        account = await account_repo.get_by_id(uuid.UUID(account_id))
        if account is None:
            raise EmailProviderNotConnectedError(
                f"No connected account found for account_id={account_id}"
            )

        return await WorkflowService(session).pull_messages(
            user, account, max_results=max_results, query=query
        )


async def _list_connected_user_ids_async(
    *, session_factory: async_sessionmaker[AsyncSession] | SessionFactory = AsyncSessionLocal
) -> list[tuple[str, str]]:
    """Return (user_id, account_id) pairs for all active users with connected accounts.

    Used by the Beat scheduler to fan out one pull task per connected account.
    """
    from sqlalchemy import select

    from app.models.connected_account import ConnectedAccount
    from app.models.user import User

    async with session_factory() as session:
        result = await session.execute(
            select(ConnectedAccount.user_id, ConnectedAccount.id)
            .join(User, User.id == ConnectedAccount.user_id)
            .where(User.is_active.is_(True))
        )
        return [
            (str(user_id), str(account_id))
            for user_id, account_id in result.all()
        ]


@celery_app.task(
    name="workflow.pull_messages",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def pull_messages_task(
    self,
    user_id: str,
    account_id: str,
    max_results: int = 12,
    query: str = DEFAULT_PULL_QUERY,
) -> dict:
    """Background task: list a user's recent mail from a connected account and
    triage each new message (same pipeline the synchronous endpoint runs inline).

    Per-message failures are already caught inside ``WorkflowService.pull_messages``
    and counted rather than raised; only a top-level failure (account not linked,
    AI not configured, a transient provider/AI API error before the loop starts)
    reaches this task boundary.

    Args:
        user_id: User UUID as string
        account_id: ConnectedAccount UUID as string
        max_results: Max messages to fetch per pull
        query: Provider-specific query string (Gmail query syntax, etc.)
    """
    try:
        return _run_async(
            _pull_messages_async(user_id, account_id, max_results, query)
        )
    except _RETRYABLE_ERRORS as exc:
        logger.warning(
            "workflow.pull_task_retrying",
            user_id=user_id,
            account_id=account_id,
            error=str(exc),
            error_type=type(exc).__name__,
            attempt=self.request.retries,
        )
        raise self.retry(exc=exc) from exc
    except (
        EmailProviderNotConnectedError,
        AINotConfiguredError,
        ValueError,
    ) as exc:
        # Permanent for this invocation — surface immediately, no retry.
        logger.warning(
            "workflow.pull_task_permanent_failure",
            user_id=user_id,
            account_id=account_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise


@celery_app.task(name="workflow.pull_all_connected")
def pull_all_connected_task(max_results: int = 12) -> dict:
    """Beat-scheduled: fan out a pull to every mailbox with a connected email
    account (Gmail, Outlook, IMAP/SMTP), so new mail is triaged automatically
    without a human clicking Sync.

    Each user's/account's pull is its own retryable, independently-failing task —
    one account's provider/AI error never blocks or fails another's.
    """
    user_account_pairs = _run_async(_list_connected_user_ids_async())
    for user_id, account_id in user_account_pairs:
        pull_messages_task.delay(user_id, account_id, max_results, DEFAULT_PULL_QUERY)
    logger.info(
        "workflow.auto_pull_fanned_out",
        account_count=len(user_account_pairs),
    )
    return {"enqueued": len(user_account_pairs)}


# Alias for backward compatibility
pull_gmail_task = pull_messages_task

