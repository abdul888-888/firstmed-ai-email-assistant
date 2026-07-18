"""Analytics & reporting API (Phase 12): triage volume, accuracy proxy, response time."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.analytics import AnalyticsSummary
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/status", summary="Module status")
async def status() -> dict:
    return {"module": "analytics", "implemented": True, "phase": 12}


@router.get(
    "/summary",
    response_model=AnalyticsSummary,
    summary="Triage volume, accuracy proxy, and response time",
)
async def summary(
    since_days: int | None = Query(
        default=None,
        ge=1,
        le=3650,
        description="Restrict to reviews created in the last N days; omit for all-time.",
    ),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AnalyticsSummary:
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=since_days) if since_days else None
    data = await AnalyticsService(session).summary(since=since)
    return AnalyticsSummary(**data)
