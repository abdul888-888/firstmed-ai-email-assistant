"""Unit tests for the AI triage service (fake AI client)."""

from __future__ import annotations

from app.services.triage_service import TriageService


class FakeAI:
    model = "claude-test"

    def __init__(self, structured_return: dict) -> None:
        self._structured = structured_return
        self.last_kwargs: dict | None = None

    async def structured(self, **kwargs):
        self.last_kwargs = kwargs
        return self._structured


async def test_classify_normalizes_confidence_and_review_flag():
    fake = FakeAI(
        {
            "intent": "prescription_refill",
            "urgency": "normal",
            "department": "nurse",
            "summary": "Patient requests a refill.",
            "requires_human_review": False,  # model said false...
            "confidence": 1.7,  # ...and returned out-of-range confidence
        }
    )
    result = await TriageService(ai=fake).classify("Refill", "Please refill my meds")

    assert result["confidence"] == 1.0  # clamped
    assert result["requires_human_review"] is True  # forced on
    assert result["department"] == "nurse"
    # schema was passed through to the model
    assert "schema" in fake.last_kwargs


async def test_classify_handles_bad_confidence_type():
    fake = FakeAI(
        {
            "intent": "other",
            "urgency": "low",
            "department": "front_office",
            "summary": "General question.",
            "requires_human_review": True,
            "confidence": "not-a-number",
        }
    )
    result = await TriageService(ai=fake).classify("Hi", "A question")
    assert result["confidence"] == 0.0
