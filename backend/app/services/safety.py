"""Safety gate: derive a review classification from a triage result (Phase 6).

Pure and dependency-free (no LLM, no I/O) so it is exhaustively unit-testable.
Maps a triage result onto the binary human-in-the-loop classification and a
human-readable reason for the review dashboard.
"""

from __future__ import annotations

from app.schemas.ai import Department, Intent, Urgency
from app.schemas.review import ReviewClassification

# Below this triage confidence, always route to a clinician regardless of intent.
CONFIDENCE_THRESHOLD = 0.70

# Intents that require clinical interpretation and must not be answered directly.
_CLINICAL_INTENTS = {Intent.medical_question.value, Intent.test_results.value}
_ESCALATED_URGENCIES = {Urgency.high.value, Urgency.urgent.value}


def classify_review(triage: dict) -> tuple[ReviewClassification, str]:
    """Return ``(classification, reason)`` for a triage result.

    ``triage`` is the dict produced by :meth:`TriageService.classify` (enum values
    are plain strings). Escalation triggers are checked in priority order so the
    reason names the most clinically significant cause.
    """
    intent = str(triage.get("intent", ""))
    urgency = str(triage.get("urgency", ""))
    department = str(triage.get("department", ""))
    try:
        confidence = float(triage.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    if intent == Intent.irrelevant.value:
        return (
            ReviewClassification.IRRELEVANT,
            "email is irrelevant to the clinic — no reply needed.",
        )
    if intent in _CLINICAL_INTENTS:
        return (
            ReviewClassification.NEEDS_PHYSICIAN_REVIEW,
            f"intent={intent} requires clinical interpretation — routed to a clinician.",
        )
    if department == Department.specialist.value:
        return (
            ReviewClassification.NEEDS_PHYSICIAN_REVIEW,
            "specialist routing — a clinician must review before sending.",
        )
    if urgency in _ESCALATED_URGENCIES:
        return (
            ReviewClassification.NEEDS_PHYSICIAN_REVIEW,
            f"urgency={urgency} — escalated for clinician review.",
        )
    if confidence < CONFIDENCE_THRESHOLD:
        return (
            ReviewClassification.NEEDS_PHYSICIAN_REVIEW,
            f"confidence {confidence:.2f} below {CONFIDENCE_THRESHOLD:.2f} — "
            "escalated for human review.",
        )
    return (
        ReviewClassification.ADMIN_DIRECT_REPLY,
        f"routine administrative request (intent={intent}, confidence {confidence:.2f}).",
    )
