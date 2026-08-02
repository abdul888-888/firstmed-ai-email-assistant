"""Provider-agnostic email API endpoints.

Exposes email operations and account connection status across all providers
(Gmail, Outlook, IMAP/SMTP) via a unified interface. All provider-specific
details are hidden behind the BaseEmailProvider abstraction.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.email import get_email_provider
from app.core.logging import get_logger
from app.models.user import User
from app.repositories.connected_account import ConnectedAccountRepository
from app.schemas.email import NormalizedEmail

logger = get_logger(__name__)
router = APIRouter(prefix="/email", tags=["email"])


@router.get("/connection", summary="Get email account connection status")
async def get_connection_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Return the connected email account status for the current user.

    Returns connected account info or {connected: false} if no account exists.
    """
    repo = ConnectedAccountRepository(session)
    account = await repo.get_by_user_id(current_user.id)

    if account is None:
        return {"connected": False}

    return {
        "connected": True,
        "provider_type": account.provider_type,
        "provider_email": account.provider_email,
        "history_id": account.history_id,
    }


@router.get("/messages", response_model=list[NormalizedEmail], summary="Fetch recent messages")
async def fetch_messages(
    max_results: int = Query(default=25, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[NormalizedEmail]:
    """Fetch recent messages from the user's connected email account.

    Returns a list of NormalizedEmail objects. Persists the new cursor
    automatically for incremental sync on next call.

    Raises 404 if no account is connected.
    """
    repo = ConnectedAccountRepository(session)
    account = await repo.get_by_user_id(current_user.id)

    if account is None:
        raise HTTPException(status_code=404, detail="No email account connected")

    provider = get_email_provider(account, session)
    messages, new_cursor = await provider.fetch_messages(
        account.history_id,
        max_results=max_results,
    )

    # Persist the cursor for next pull.
    if new_cursor is not None:
        await repo.update_history_id(account, history_id=new_cursor)

    return messages


@router.post("/drafts", summary="Create a draft email")
async def create_draft(
    payload: dict,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Create a draft email in the user's email account.

    Request body:
    {
        "to": "recipient@example.com",
        "subject": "Subject line",
        "body": "Message body",
        "thread_id": "optional_thread_id"
    }

    Raises 404 if no account is connected.
    Returns {draft_id: "provider_draft_id"}.
    """
    repo = ConnectedAccountRepository(session)
    account = await repo.get_by_user_id(current_user.id)

    if account is None:
        raise HTTPException(status_code=404, detail="No email account connected")

    provider = get_email_provider(account, session)
    draft_id = await provider.create_draft(
        to=payload.get("to", ""),
        subject=payload.get("subject", ""),
        body=payload.get("body", ""),
        thread_id=payload.get("thread_id"),
    )

    return {"draft_id": draft_id}
