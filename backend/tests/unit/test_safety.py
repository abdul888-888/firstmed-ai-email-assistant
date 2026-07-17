"""Unit tests for the safety-gate classification (pure, no LLM)."""

from __future__ import annotations

import pytest
from app.schemas.review import ReviewClassification
from app.services.safety import CONFIDENCE_THRESHOLD, classify_review

ADMIN = ReviewClassification.ADMIN_DIRECT_REPLY
REVIEW = ReviewClassification.NEEDS_PHYSICIAN_REVIEW


def _triage(**over):
    base = {
        "intent": "appointment",
        "urgency": "normal",
        "department": "front_office",
        "confidence": 0.95,
        "summary": "s",
    }
    base.update(over)
    return base


@pytest.mark.parametrize(
    "triage,expected",
    [
        # Happy admin path.
        (_triage(), ADMIN),
        (_triage(intent="billing_insurance", department="front_office"), ADMIN),
        (_triage(intent="prescription_refill", department="nurse"), ADMIN),
        # Clinical intents escalate regardless of confidence.
        (_triage(intent="medical_question", confidence=0.99), REVIEW),
        (_triage(intent="test_results", confidence=0.99), REVIEW),
        # Specialist routing escalates.
        (_triage(department="specialist"), REVIEW),
        # Urgency escalates.
        (_triage(urgency="high"), REVIEW),
        (_triage(urgency="urgent"), REVIEW),
        # Confidence boundary: below threshold escalates, at/above stays admin.
        (_triage(confidence=CONFIDENCE_THRESHOLD - 0.01), REVIEW),
        (_triage(confidence=CONFIDENCE_THRESHOLD), ADMIN),
    ],
)
def test_classify_review_truth_table(triage, expected):
    classification, reason = classify_review(triage)
    assert classification == expected
    assert isinstance(reason, str) and reason  # always explains the decision


def test_classify_review_handles_bad_confidence():
    # Non-numeric confidence is treated as 0.0 → escalate.
    classification, _ = classify_review(_triage(confidence="n/a"))
    assert classification == REVIEW
