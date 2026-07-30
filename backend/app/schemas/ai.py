"""Schemas for AI triage + draft generation (Phase 5)."""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field


class Intent(str, enum.Enum):
    appointment = "appointment"
    prescription_refill = "prescription_refill"
    billing_insurance = "billing_insurance"
    medical_question = "medical_question"
    test_results = "test_results"
    referral = "referral"
    complaint = "complaint"
    irrelevant = "irrelevant"
    other = "other"


class Urgency(str, enum.Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class Department(str, enum.Enum):
    front_office = "front_office"
    nurse = "nurse"
    specialist = "specialist"
    # Domain-specific routing (requirement B): a deterministic keyword layer in
    # app.services.safety can annotate/override these regardless of the LLM's
    # own department pick, so lab/gastro/physio emails route more precisely
    # than the generic buckets above.
    laboratory = "laboratory"
    gastroenterology = "gastroenterology"
    physiotherapy = "physiotherapy"


class EmailInput(BaseModel):
    subject: str = ""
    body: str = Field(min_length=1)


class TriageResult(BaseModel):
    intent: Intent
    urgency: Urgency
    department: Department
    summary: str
    requires_human_review: bool = True
    confidence: float = Field(ge=0.0, le=1.0)


class DraftRequest(EmailInput):
    use_context: bool = True


class Citation(BaseModel):
    document_id: str
    source: str
    title: str
    url: str | None = None


class DraftResult(BaseModel):
    draft: str
    model: str
    citations: list[Citation] = Field(default_factory=list)
    # Human-in-the-loop guardrail — the reply is never sent automatically.
    requires_human_review: bool = True
