"""Phase 12 analytics: triage volume, response time, and an accuracy proxy.

``DraftReview`` records no ground-truth field for what a human corrected the
AI's triage to — the only human-outcome signal is the approve/reject/send
lifecycle. So "triage accuracy" here is necessarily a proxy: the share of
*decided* drafts (approved or sent) that a human did **not** reject. This is
documented on :class:`~app.schemas.analytics.AnalyticsSummary` as well so the
approximation is visible to API consumers, not just this module.
"""

from __future__ import annotations

import datetime as dt
import statistics

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.analytics import AnalyticsRepository
from app.schemas.review import ReviewStatus


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = AnalyticsRepository(session)

    async def summary(self, *, since: dt.datetime | None = None) -> dict:
        by_status = await self.repo.counts_by_status(since=since)
        by_department = await self.repo.counts_by_department(since=since)
        timestamps = await self.repo.lifecycle_timestamps(since=since)

        total = sum(by_status.values())
        approved = by_status.get(ReviewStatus.approved.value, 0)
        rejected = by_status.get(ReviewStatus.rejected.value, 0)
        sent = by_status.get(ReviewStatus.sent.value, 0)
        decided = approved + rejected + sent

        decision_seconds = [
            (reviewed_at - created_at).total_seconds()
            for created_at, reviewed_at, _ in timestamps
            if reviewed_at is not None
        ]
        turnaround_seconds = [
            (sent_at - created_at).total_seconds()
            for created_at, _, sent_at in timestamps
            if sent_at is not None
        ]

        return {
            "total_processed": total,
            "counts_by_status": by_status,
            "counts_by_department": by_department,
            "decided_count": decided,
            "rejected_count": rejected,
            "triage_accuracy_rate": (decided - rejected) / decided if decided else None,
            "avg_decision_seconds": (
                statistics.fmean(decision_seconds) if decision_seconds else None
            ),
            "avg_turnaround_seconds": (
                statistics.fmean(turnaround_seconds) if turnaround_seconds else None
            ),
        }
