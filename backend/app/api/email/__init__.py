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
    department: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[NormalizedEmail]:
    """Fetch recent messages from the user's connected email account.

    Returns a list of NormalizedEmail objects. Persists the new cursor
    automatically for incremental sync on next call.
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

    # Department Isolation Logic
    user_role = current_user.role.value.upper() if hasattr(current_user.role, "value") else str(current_user.role).upper()
    active_dept = department or getattr(current_user, "department", "FRONT_OFFICE")

    # Non-admin users are restricted to their assigned department role
    if user_role != "ADMIN":
        target_dept = user_role
    else:
        target_dept = active_dept.upper()

    # Filter messages if target_dept specified
    filtered = []
    for msg in messages:
        # If message does not have department tag or matches target_dept
        msg_dept = getattr(msg, "target_department", None) or getattr(msg, "department", None)
        if msg_dept is None or msg_dept.upper() == target_dept:
            filtered.append(msg)

    return filtered if (department or user_role != "ADMIN") else messages


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


@router.post("/{email_id}/reassign", summary="Re-assign email to another department")
async def reassign_email(
    email_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Re-assign email target department and add an internal note."""
    target_department = payload.get("target_department", "").upper()
    note_content = payload.get("note", "")

    if not target_department:
        raise HTTPException(status_code=400, detail="target_department is required")

    from app.models.internal_note import InternalNote

    note = InternalNote(
        email_id=email_id,
        author_id=current_user.id,
        author_name=current_user.full_name or current_user.email,
        author_role=current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        content=f"Transferred to {target_department}. {note_content}".strip(),
        mentioned_department=target_department,
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)

    logger.info("email.reassigned", email_id=email_id, target_department=target_department, by=str(current_user.id))

    return {
        "status": "success",
        "email_id": email_id,
        "target_department": target_department,
        "note_id": str(note.id),
    }


@router.get("/{email_id}/notes", summary="List internal notes for an email")
async def list_email_notes(
    email_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """List all internal notes for a specific email."""
    from sqlalchemy import select
    from app.models.internal_note import InternalNote

    stmt = select(InternalNote).where(InternalNote.email_id == email_id).order_by(InternalNote.created_at.desc())
    res = await session.execute(stmt)
    notes = res.scalars().all()

    return {
        "notes": [
            {
                "id": str(n.id),
                "email_id": n.email_id,
                "author_id": str(n.author_id),
                "author_name": n.author_name,
                "author_role": n.author_role,
                "content": n.content,
                "mentioned_department": n.mentioned_department,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes
        ],
        "count": len(notes),
    }


@router.post("/{email_id}/notes", summary="Add an internal note to an email")
async def add_email_note(
    email_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Add an internal note with optional @mention department."""
    content = payload.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    mentioned_dept = payload.get("mentioned_department")

    from app.models.internal_note import InternalNote

    note = InternalNote(
        email_id=email_id,
        author_id=current_user.id,
        author_name=current_user.full_name or current_user.email,
        author_role=current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        content=content,
        mentioned_department=mentioned_dept,
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)

    return {
        "id": str(note.id),
        "email_id": note.email_id,
        "author_id": str(note.author_id),
        "author_name": note.author_name,
        "author_role": note.author_role,
        "content": note.content,
        "mentioned_department": note.mentioned_department,
        "created_at": note.created_at.isoformat() if note.created_at else None,
    }
