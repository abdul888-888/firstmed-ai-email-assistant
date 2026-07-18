"""Aggregate queries backing the Phase 12 analytics dashboard.

Timestamp differences are computed in Python (not SQL date arithmetic) so the
same code runs unchanged against the SQLite test suite and PostgreSQL, matching
the portability approach used elsewhere for ``DraftReview``.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft_review import DraftReview

LifecycleRow = tuple[dt.datetime, "dt.datetime | None", "dt.datetime | None"]


class AnalyticsRepository:
    """Read-only aggregate queries over :class:`~app.models.draft_review.DraftReview`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def counts_by_status(self, *, since: dt.datetime | None = None) -> dict[str, int]:
        stmt = select(DraftReview.status, func.count())
        if since is not None:
            stmt = stmt.where(DraftReview.created_at >= since)
        stmt = stmt.group_by(DraftReview.status)
        result = await self.session.execute(stmt)
        return dict(result.all())

    async def counts_by_department(self, *, since: dt.datetime | None = None) -> dict[str, int]:
        stmt = select(DraftReview.department, func.count())
        if since is not None:
            stmt = stmt.where(DraftReview.created_at >= since)
        stmt = stmt.group_by(DraftReview.department)
        result = await self.session.execute(stmt)
        return dict(result.all())

    async def lifecycle_timestamps(self, *, since: dt.datetime | None = None) -> list[LifecycleRow]:
        """``(created_at, reviewed_at, sent_at)`` for every review — response-time inputs."""
        stmt = select(DraftReview.created_at, DraftReview.reviewed_at, DraftReview.sent_at)
        if since is not None:
            stmt = stmt.where(DraftReview.created_at >= since)
        result = await self.session.execute(stmt)
        return [tuple(row) for row in result.all()]
