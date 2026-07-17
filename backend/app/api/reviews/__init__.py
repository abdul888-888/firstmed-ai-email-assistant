"""Review queue API (Phase 8): inspect, edit, approve, reject, and send AI drafts.

Lifecycle: ``pending`` --edit--> (still pending) --approve--> ``approved``
(draft created in Gmail) --send--> ``sent`` (delivered). A pending review can
instead be ``rejected``. Approve creates a Gmail draft (never sends); send is the
only outward-facing action and requires an already-approved review.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.user import User
from app.repositories.draft_review import DraftReviewRepository
from app.schemas.review import (
    DraftReviewRead,
    ReviewEdit,
    ReviewList,
    ReviewReject,
    ReviewStatus,
)
from app.services.gmail_service import GmailApiError, GmailNotConnectedError
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/reviews", tags=["reviews"])
logger = get_logger(__name__)

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
_NOT_CONNECTED = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="Google account is not connected.",
)


async def _load_owned(review_id: str, user: User, session: AsyncSession):
    try:
        rid = uuid.UUID(review_id)
    except ValueError as exc:
        raise _NOT_FOUND from exc
    review = await DraftReviewRepository(session).get(rid)
    # Scope to the owner so one user can't read/act on another's reviews.
    if review is None or review.user_id != user.id:
        raise _NOT_FOUND
    return review


def _require_status(review, expected: ReviewStatus) -> None:
    if review.status != expected.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Review is {review.status}, expected {expected.value}.",
        )


@router.get("", response_model=ReviewList, summary="List reviews by status")
async def list_reviews(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    review_status: ReviewStatus = Query(default=ReviewStatus.pending, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> ReviewList:
    rows = await DraftReviewRepository(session).list_by_status(
        current_user.id, review_status.value, limit=limit
    )
    return ReviewList(
        reviews=[DraftReviewRead.model_validate(r) for r in rows],
        count=len(rows),
    )


@router.get(
    "/pending",
    response_model=ReviewList,
    summary="List pending AI drafts awaiting human review",
)
async def list_pending(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
) -> ReviewList:
    rows = await DraftReviewRepository(session).list_pending(current_user.id, limit=limit)
    return ReviewList(
        reviews=[DraftReviewRead.model_validate(r) for r in rows],
        count=len(rows),
    )


@router.get(
    "/{review_id}",
    response_model=DraftReviewRead,
    summary="Fetch a single review (full draft + reasoning)",
)
async def get_review(
    review_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DraftReviewRead:
    review = await _load_owned(review_id, current_user, session)
    return DraftReviewRead.model_validate(review)


@router.patch(
    "/{review_id}",
    response_model=DraftReviewRead,
    summary="Edit the drafted reply text (pending only)",
)
async def edit_review(
    review_id: str,
    payload: ReviewEdit,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DraftReviewRead:
    review = await _load_owned(review_id, current_user, session)
    _require_status(review, ReviewStatus.pending)
    updated = await DraftReviewRepository(session).update_body(
        review, draft_body=payload.draft_body
    )
    return DraftReviewRead.model_validate(updated)


@router.post(
    "/{review_id}/approve",
    response_model=DraftReviewRead,
    summary="Approve a review → push the draft to Gmail Drafts (never sends)",
)
async def approve_review(
    review_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DraftReviewRead:
    review = await _load_owned(review_id, current_user, session)
    _require_status(review, ReviewStatus.pending)
    try:
        updated = await WorkflowService(session).approve(current_user, review)
    except GmailNotConnectedError as exc:
        raise _NOT_CONNECTED from exc
    except GmailApiError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gmail draft creation failed: {exc}",
        ) from exc
    return DraftReviewRead.model_validate(updated)


@router.post(
    "/{review_id}/reject",
    response_model=DraftReviewRead,
    summary="Reject a pending review with a reason",
)
async def reject_review(
    review_id: str,
    payload: ReviewReject,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DraftReviewRead:
    review = await _load_owned(review_id, current_user, session)
    _require_status(review, ReviewStatus.pending)
    updated = await WorkflowService(session).reject(current_user, review, payload.reason)
    return DraftReviewRead.model_validate(updated)


@router.post(
    "/{review_id}/send",
    response_model=DraftReviewRead,
    summary="Send an approved review's draft via Gmail (outward-facing)",
)
async def send_review(
    review_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DraftReviewRead:
    review = await _load_owned(review_id, current_user, session)
    _require_status(review, ReviewStatus.approved)
    try:
        updated = await WorkflowService(session).send(current_user, review)
    except GmailNotConnectedError as exc:
        raise _NOT_CONNECTED from exc
    except GmailApiError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gmail send failed: {exc}",
        ) from exc
    return DraftReviewRead.model_validate(updated)
