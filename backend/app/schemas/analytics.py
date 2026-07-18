"""Schemas for the Phase 12 analytics dashboard."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyticsSummary(BaseModel):
    """Triage volume, response time, and an approve-rate accuracy proxy.

    ``triage_accuracy_rate`` is an approximation, not a true ground-truth
    accuracy: the underlying model has no field capturing what a human
    corrected the AI's triage to, so it is computed as the share of decided
    drafts (approved or sent) that were **not** rejected.
    """

    total_processed: int = 0
    counts_by_status: dict[str, int] = Field(default_factory=dict)
    counts_by_department: dict[str, int] = Field(default_factory=dict)
    decided_count: int = 0
    rejected_count: int = 0
    triage_accuracy_rate: float | None = None
    avg_decision_seconds: float | None = None
    avg_turnaround_seconds: float | None = None
