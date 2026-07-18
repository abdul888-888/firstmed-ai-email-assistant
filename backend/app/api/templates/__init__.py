"""Template management API (Phase 7): canned administrative responses.

Staff read these on the review dashboard and insert them into an AI draft before
approving. Read-only over the API for now (templates are seeded/curated); editing
UI is a later concern.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.repositories.template import TemplateRepository
from app.schemas.template import TemplateCategory, TemplateList, TemplateRead

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
