"""Unit tests for the safety-gate classification (pure, no LLM)."""

from __future__ import annotations

import pytest
from app.schemas.review import ReviewClassification
from app.services.safety import CONFIDENCE_THRESHOLD, classify_review

ADMIN = ReviewClassification.ADMIN_DIRECT_REPLY
REVIEW = ReviewClassification.NEEDS_PHYSICIAN_REVIEW
STAFF = ReviewClassification.ROUTE_TO_STAFF
IRRELEVANT = ReviewClassification.IRRELEVANT


def _triage(**over):
    base = {
        "intent": "billing_insurance",
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
        # Happy admin path — a genuine administrative question.
        (_triage(), ADMIN),
        (_triage(intent="billing_insurance", department="front_office"), ADMIN),
        (_triage(intent="prescription_refill", department="nurse"), ADMIN),
        (_triage(intent="other", department="front_office"), ADMIN),
        # Appointments must NEVER be drafted — routed to staff.
        (_triage(intent="appointment"), STAFF),
        # Complaints must NEVER be drafted — routed to staff.
        (_triage(intent="complaint"), STAFF),
        # Clinical intents escalate to a clinician regardless of confidence.
        (_triage(intent="medical_question", confidence=0.99), REVIEW),
        (_triage(intent="test_results", confidence=0.99), REVIEW),
        # Specialist routing escalates.
        (_triage(department="specialist"), REVIEW),
        # Urgency escalates.
        (_triage(urgency="high"), REVIEW),
        (_triage(urgency="urgent"), REVIEW),
        # Irrelevant / spam.
        (_triage(intent="irrelevant"), IRRELEVANT),
        # Confidence boundary: below threshold escalates, at/above stays admin.
        (_triage(confidence=CONFIDENCE_THRESHOLD - 0.01), REVIEW),
        (_triage(confidence=CONFIDENCE_THRESHOLD), ADMIN),
    ],
)
def test_classify_review_truth_table(triage, expected):
    decision = classify_review(triage)
    assert decision.classification == expected
    assert isinstance(decision.reason, str) and decision.reason  # always explains the decision


def test_classify_review_handles_bad_confidence():
    # Non-numeric confidence is treated as 0.0 → escalate.
    decision = classify_review(_triage(confidence="n/a"))
    assert decision.classification == REVIEW


def test_classify_review_default_department_carries_through():
    # No specialty keyword hit → the LLM's own department passes through unchanged.
    decision = classify_review(_triage(department="nurse"))
    assert decision.department == "nurse"


# --- Deterministic keyword gates override a mis-triaged intent ----------------


def test_emergency_keyword_overrides_benign_intent():
    # The LLM mislabels a chest-pain email as routine billing; the emergency
    # gate must still escalate it to a clinician.
    decision = classify_review(
        _triage(intent="billing_insurance", confidence=0.99),
        text="Subject: bill\n\nI have severe chest pain and shortness of breath.",
    )
    assert decision.classification == REVIEW
    assert "emergency" in decision.reason.lower()


def test_legal_keyword_routes_to_staff():
    decision = classify_review(
        _triage(intent="other", confidence=0.99),
        text="My attorney will be in touch about a malpractice claim.",
    )
    assert decision.classification == STAFF


def test_billing_dispute_keyword_routes_to_staff():
    # A billing email that is actually a dispute must not be auto-drafted even
    # though billing_insurance is normally an admin-answerable intent.
    decision = classify_review(
        _triage(intent="billing_insurance", confidence=0.99),
        text="You overcharged me and I want a refund for the double charged visit.",
    )
    assert decision.classification == STAFF


def test_plain_billing_question_still_admin_with_text():
    # A genuine insurance/pricing question (no dispute language) stays admin.
    decision = classify_review(
        _triage(intent="billing_insurance", confidence=0.99),
        text="Do you accept Aetna insurance and how much is a routine visit?",
    )
    assert decision.classification == ADMIN


# --- Laboratory (requirement B) ----------------------------------------------


def test_lab_results_request_escalates_even_if_mistriaged():
    # THE key gap this closes: the LLM tags this as routine "other" (mistake),
    # but asking for actual results must never reach a draft.
    decision = classify_review(
        _triage(intent="other", confidence=0.99),
        text="Hi, I was wondering if my blood test results are ready yet?",
    )
    assert decision.classification == REVIEW
    assert decision.department == "laboratory"


def test_lab_appointment_request_routes_to_staff():
    decision = classify_review(
        _triage(intent="other", confidence=0.99),
        text="Can I book a blood test for next Tuesday morning?",
    )
    assert decision.classification == STAFF
    assert decision.department == "laboratory"


def test_lab_preparation_question_is_admin_eligible_and_tagged():
    # Preparation questions ARE allowed to be drafted (annotation only — the
    # classification is whatever the normal path would produce).
    decision = classify_review(
        _triage(intent="other", department="front_office", confidence=0.9),
        text="Do I need to fast before my blood test tomorrow?",
    )
    assert decision.classification == ADMIN
    assert decision.department == "laboratory"


def test_lab_prep_keyword_does_not_bypass_clinical_escalation():
    # Fail-safe check: a genuinely clinical message that happens to mention lab
    # prep language must still escalate — the prep gate only ANNOTATES, it must
    # never downgrade an existing escalation.
    decision = classify_review(
        _triage(intent="test_results", confidence=0.99),
        text="I'm fasting like you said, but my last test results showed high glucose, what should I do?",
    )
    assert decision.classification == REVIEW


# --- Gastroenterology (requirement B) ----------------------------------------


def test_gastro_procedure_booking_routes_to_staff_not_generic():
    decision = classify_review(
        _triage(intent="appointment", department="front_office", confidence=0.9),
        text="I'd like to schedule a colonoscopy next month.",
    )
    assert decision.classification == STAFF
    assert decision.department == "gastroenterology"


def test_gastro_general_mention_is_annotated_not_forced():
    # A general gastro mention doesn't force an outcome — it only tags the
    # department; the normal admin path still applies here since nothing else
    # about this email is clinical/urgent/low-confidence.
    decision = classify_review(
        _triage(intent="other", department="front_office", confidence=0.9),
        text="I'd like to schedule a consultation with a gastroenterologist about my heartburn.",
    )
    assert decision.department == "gastroenterology"
    # (classification depends on whatever intent/urgency the LLM gave — here
    # "other"/0.9/normal — so it lands ADMIN, demonstrating annotation-only.)
    assert decision.classification == ADMIN


def test_gastro_symptom_email_still_escalates_via_existing_clinical_path():
    # Symptom-described gastro emails are NOT swept into "general consult" —
    # existing clinical-intent escalation still applies untouched.
    decision = classify_review(
        _triage(intent="medical_question", confidence=0.99),
        text="I've had severe abdominal pain for three days, is this serious?",
    )
    assert decision.classification == REVIEW


# --- Physiotherapy (requirement B) -------------------------------------------


def test_physio_without_referral_routes_to_staff_never_drafted():
    decision = classify_review(
        _triage(intent="appointment", department="front_office", confidence=0.9),
        text="I'd like to book physio for my shoulder.",
    )
    assert decision.classification == STAFF
    assert decision.department == "physiotherapy"
    assert "referral" in decision.reason.lower()


def test_physio_with_referral_evidence_routes_to_staff_for_direct_booking():
    decision = classify_review(
        _triage(intent="appointment", department="front_office", confidence=0.9),
        text="My orthopaedic consult cleared me for physio — can I book an appointment?",
    )
    assert decision.classification == STAFF
    assert decision.department == "physiotherapy"
    assert "direct booking" in decision.reason.lower()


def test_physio_word_boundary_does_not_match_unrelated_word():
    # "physio" must not match as a substring of an unrelated word.
    decision = classify_review(
        _triage(intent="billing_insurance", department="front_office", confidence=0.9),
        text="Please see the physiographic map attached for directions to the clinic.",
    )
    assert decision.department != "physiotherapy"
