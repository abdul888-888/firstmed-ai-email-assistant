"""Administration API — internal collaboration engine (Phase 11).

Assigning reviews to staff and attaching internal collaboration notes. Other
admin surfaces (workflows/users/config administration, Phases 12-13) are not
yet implemented.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.draft_review import DraftReview
from app.models.user import User
from app.repositories.draft_review import DraftReviewRepository
from app.repositories.user import UserRepository
from app.schemas.collaboration import (
    ReviewAssign,
    ReviewNoteCreate,
    ReviewNoteList,
    ReviewNoteRead,
)
from app.schemas.review import DraftReviewRead
from app.schemas.user import UserList, UserRead
from app.services.collaboration_service import AssigneeNotFoundError, CollaborationService

router = APIRouter(prefix="/admin", tags=["admin"])
logger = get_logger(__name__)

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")


@router.get("/status", summary="Module status")
async def module_status() -> dict:
    return {"module": "admin", "implemented": True, "phase": 11}


@router.get(
    "/users",
    response_model=UserList,
    summary="List active staff (for assignment pickers)",
)
async def list_users(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UserList:
    users = await UserRepository(session).list_active()
    return UserList(users=[UserRead.model_validate(u) for u in users], count=len(users))


async def _load_review(review_id: str, session: AsyncSession) -> DraftReview:
    """Load a review by id, regardless of owner (collaboration spans users)."""
    try:
        rid = uuid.UUID(review_id)
    except ValueError as exc:
        raise _NOT_FOUND from exc
    review = await DraftReviewRepository(session).get(rid)
    if review is None:
        raise _NOT_FOUND
    return review


@router.patch(
    "/reviews/{review_id}/assign",
    response_model=DraftReviewRead,
    summary="Assign (or unassign) a review to a staff member",
)
async def assign_review(
    review_id: str,
    payload: ReviewAssign,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DraftReviewRead:
    review = await _load_review(review_id, session)
    try:
        updated = await CollaborationService(session).assign(review, payload.assigned_to)
    except AssigneeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return DraftReviewRead.model_validate(updated)


@router.get(
    "/reviews/{review_id}/notes",
    response_model=ReviewNoteList,
    summary="List internal collaboration notes on a review",
)
async def list_notes(
    review_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ReviewNoteList:
    review = await _load_review(review_id, session)
    notes = await CollaborationService(session).list_notes(review)
    return ReviewNoteList(
        notes=[ReviewNoteRead.model_validate(n) for n in notes],
        count=len(notes),
    )


@router.post(
    "/reviews/{review_id}/notes",
    response_model=ReviewNoteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add an internal collaboration note to a review",
)
async def add_note(
    review_id: str,
    payload: ReviewNoteCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ReviewNoteRead:
    review = await _load_review(review_id, session)
    note = await CollaborationService(session).add_note(review, current_user, payload.body)
    return ReviewNoteRead.model_validate(note)
