"""Administration API — internal collaboration engine (Phase 11).

Assigning reviews to staff and attaching internal collaboration notes. Other
admin surfaces (workflows/users/config administration, Phases 12-13) are not
yet implemented.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.draft_review import DraftReview
from app.models.user import User, UserRole
from app.repositories.draft_review import DraftReviewRepository
from app.repositories.user import UserRepository
from app.schemas.collaboration import (
    ReviewAssign,
    ReviewNoteCreate,
    ReviewNoteList,
    ReviewNoteRead,
)
from app.schemas.review import DraftReviewRead
from app.schemas.user import UserCreate, UserList, UserRead, UserUpdate
from app.core.security import hash_password
from app.services.collaboration_service import CollaborationService

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
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_db),
) -> UserList:
    users = await UserRepository(session).list_active()
    return UserList(users=[UserRead.model_validate(u) for u in users], count=len(users))


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a staff user (Admin only)",
)
async def create_user(
    payload: UserCreate,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_db),
) -> UserRead:
    repo = UserRepository(session)
    if await repo.get_by_email(payload.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )
    user = await repo.create(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        department=payload.department,
        is_on_shift=payload.is_on_shift,
    )
    return UserRead.model_validate(user)


@router.put(
    "/users/{user_id}",
    response_model=UserRead,
    summary="Update a staff user role/department/shift (Admin only)",
)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_db),
) -> UserRead:
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.role is not None:
        user.role = payload.role
    if payload.department is not None:
        user.department = payload.department
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.is_on_shift is not None:
        user.is_on_shift = payload.is_on_shift
        
    await session.commit()
    await session.refresh(user)
    return UserRead.model_validate(user)


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


# --- Routing Rules & Audit Log (Design Spec §6) ---

_IN_MEMORY_ROUTING_RULES = [
    {"id": "rule-1", "category": "Pricing & Insurance", "target_queue": "front_office", "condition": "auto_match", "enabled": True},
    {"id": "rule-2", "category": "Lab & Pathology", "target_queue": "laboratory", "condition": "lab_results_safety_suppression", "enabled": True},
    {"id": "rule-3", "category": "Physiotherapy Scheduling", "target_queue": "physiotherapy", "condition": "direct_booking", "enabled": True},
    {"id": "rule-4", "category": "Clinical Specialist Query", "target_queue": "nurse_specialist", "condition": "triage_required", "enabled": True},
]

_IN_MEMORY_AUDIT_LOG = [
    {"id": "log-101", "actor": "Admin (system)", "action": "ROUTING_RULE_UPDATED", "target": "Lab & Pathology", "timestamp": "2026-08-06T14:10:00Z", "details": "Enabled safety suppression rule"},
    {"id": "log-102", "actor": "Front Office", "action": "DRAFT_APPROVED", "target": "Msg #942", "timestamp": "2026-08-06T14:25:00Z", "details": "Approved GP pricing reply"},
    {"id": "log-103", "actor": "Dr. Sarah", "action": "SPECIALIST_GUIDANCE_ADDED", "target": "Msg #945", "timestamp": "2026-08-06T14:40:00Z", "details": "Provided physio recovery plan"},
]


@router.get("/routing-rules", summary="List routing rules (Admin only)")
async def list_routing_rules(
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict:
    return {"rules": _IN_MEMORY_ROUTING_RULES, "count": len(_IN_MEMORY_ROUTING_RULES)}


@router.post("/routing-rules", summary="Add routing rule (Admin only)")
async def create_routing_rule(
    payload: dict,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict:
    new_rule = {
        "id": f"rule-{uuid.uuid4().hex[:6]}",
        "category": payload.get("category", "General"),
        "target_queue": payload.get("target_queue", "front_office"),
        "condition": payload.get("condition", "auto_match"),
        "enabled": payload.get("enabled", True),
    }
    _IN_MEMORY_ROUTING_RULES.append(new_rule)
    _IN_MEMORY_AUDIT_LOG.insert(0, {
        "id": f"log-{uuid.uuid4().hex[:6]}",
        "actor": current_user.full_name or current_user.email,
        "action": "ROUTING_RULE_CREATED",
        "target": new_rule["category"],
        "timestamp": "2026-08-06T15:00:00Z",
        "details": f"Created rule mapping to {new_rule['target_queue']}",
    })
    return new_rule


@router.put("/routing-rules/{rule_id}", summary="Update routing rule (Admin only)")
async def update_routing_rule(
    rule_id: str,
    payload: dict,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict:
    for rule in _IN_MEMORY_ROUTING_RULES:
        if rule["id"] == rule_id:
            rule.update({k: v for k, v in payload.items() if v is not None})
            return rule
    raise HTTPException(status_code=404, detail="Routing rule not found")


@router.delete("/routing-rules/{rule_id}", summary="Delete routing rule (Admin only)")
async def delete_routing_rule(
    rule_id: str,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict:
    global _IN_MEMORY_ROUTING_RULES
    _IN_MEMORY_ROUTING_RULES = [r for r in _IN_MEMORY_ROUTING_RULES if r["id"] != rule_id]
    return {"success": True}


@router.get("/audit-log", summary="Get audit log feed (Admin only)")
async def get_audit_log(
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict:
    return {"logs": _IN_MEMORY_AUDIT_LOG, "count": len(_IN_MEMORY_AUDIT_LOG)}


@router.post("/users/invite", summary="Invite a new staff member (Admin only)")
async def invite_user(
    payload: dict,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict:
    email = payload.get("email", "").strip()
    role = payload.get("role", "FRONT_OFFICE")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    
    invite_token = f"invite_{uuid.uuid4().hex[:12]}"
    invite_link = f"/login?invite_token={invite_token}&email={email}"
    
    _IN_MEMORY_AUDIT_LOG.insert(0, {
        "id": f"log-{uuid.uuid4().hex[:6]}",
        "actor": current_user.full_name or current_user.email,
        "action": "STAFF_INVITED",
        "target": email,
        "timestamp": "2026-08-06T15:10:00Z",
        "details": f"Invited with role {role}",
    })
    return {"success": True, "email": email, "invite_token": invite_token, "invite_link": invite_link}

