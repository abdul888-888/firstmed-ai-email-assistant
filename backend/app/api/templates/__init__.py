"""Template management API (Phase 7): canned administrative responses.

Staff read these on the review dashboard and insert them into an AI draft before
approving. Read-only over the API for now (templates are seeded/curated); editing
UI is a later concern.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.user import User, UserRole
from app.repositories.template import TemplateRepository
from app.schemas.template import TemplateCategory, TemplateList, TemplateRead, TemplateWrite

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("/status", summary="Module status")
async def status_() -> dict:
    return {"module": "templates", "implemented": True, "phase": 7}


@router.get("", response_model=TemplateList, summary="List canned-response templates")
async def list_templates(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    category: TemplateCategory | None = Query(default=None),
    active: bool = Query(default=True, description="Only active templates"),
) -> TemplateList:
    rows = await TemplateRepository(session).list(
        category=category.value if category else None, active_only=active
    )
    return TemplateList(
        templates=[TemplateRead.model_validate(t) for t in rows],
        count=len(rows),
    )


@router.get("/{template_id}", response_model=TemplateRead, summary="Fetch a single template")
async def get_template(
    template_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TemplateRead:
    tpl = await TemplateRepository(session).get(template_id)
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return TemplateRead.model_validate(tpl)


@router.post("", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateWrite,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_db),
) -> TemplateRead:
    tpl = await TemplateRepository(session).upsert(
        key=payload.key,
        title=payload.title,
        category=payload.category.value,
        body=payload.body,
        is_active=payload.is_active,
    )
    return TemplateRead.model_validate(tpl)


@router.put("/{template_id}", response_model=TemplateRead)
async def update_template(
    template_id: uuid.UUID,
    payload: TemplateWrite,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_db),
) -> TemplateRead:
    repo = TemplateRepository(session)
    existing = await repo.get(template_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    if payload.key != existing.key:
        conflict = await repo.get_by_key(payload.key)
        if conflict is not None and conflict.id != existing.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Template key already exists")
    existing.key = payload.key
    existing.title = payload.title
    existing.category = payload.category.value
    existing.body = payload.body
    existing.is_active = payload.is_active
    await session.commit()
    await session.refresh(existing)
    return TemplateRead.model_validate(existing)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_template(
    template_id: uuid.UUID,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_db),
) -> Response:
    repo = TemplateRepository(session)
    tpl = await repo.get(template_id)
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    await repo.delete(tpl)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
