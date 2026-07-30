"""Safety gate: derive a review classification from a triage result (Phase 6).

Pure and dependency-free (no LLM, no I/O) so it is exhaustively unit-testable.
Maps a triage result onto a human-in-the-loop classification and a human-readable
reason for the review dashboard.

Safety model (why this exists): the LLM triage is advisory only. The hard
exclusions below are enforced *deterministically* in code — an email that names
an appointment, a complaint, a legal matter, a billing dispute, an emergency, or
a domain-specific exclusion (lab results, a gastro procedure booking, a physio
referral) can never reach draft generation, regardless of what the model
decided. Only ``ADMIN_DIRECT_REPLY`` is eligible for an AI draft (see
``WorkflowService``).

Design rule for every deterministic gate in this module: a keyword match may
only RESTRICT (push toward NEEDS_PHYSICIAN_REVIEW / ROUTE_TO_STAFF) or ANNOTATE
(tag ``department`` without changing the classification) — never PERMIT or
DOWNGRADE. A gate that could turn a would-be-escalated email into a draft on an
incidental keyword match reintroduces the exact failure this file exists to
close. Where a rule only narrows *which* department/team should own an
existing routing outcome (e.g. lab prep, general gastro mentions), it must not
touch the classification at all — it only overrides ``department``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.ai import Department, Intent, Urgency
from app.schemas.review import ReviewClassification

# Below this triage confidence, always route to a human regardless of intent
# (covers the "unclear or conflicting information" exclusion).
CONFIDENCE_THRESHOLD = 0.70

# Intents that require clinical interpretation and must not be answered directly.
_CLINICAL_INTENTS = {Intent.medical_question.value, Intent.test_results.value}
_ESCALATED_URGENCIES = {Urgency.high.value, Urgency.urgent.value}

# Non-clinical intents that must always be handled by a staff member, never
# AI-drafted (appointment booking/changes/cancellations and complaints).
_ROUTE_TO_STAFF_INTENTS = {Intent.appointment.value, Intent.complaint.value}


@dataclass(slots=True)
class SafetyDecision:
    """The safety gate's verdict: outcome, human-readable reason, and the
    department that should own it (may differ from the LLM's own pick — see
    module docstring)."""

    classification: ReviewClassification
    reason: str
    department: str


def _kw(*words: str) -> re.Pattern[str]:
    """Case-insensitive matcher for any of ``words`` as a phrase/substring."""
    return re.compile("|".join(re.escape(w) for w in words), re.IGNORECASE)


# Deterministic keyword gates on the raw email text. These OVERRIDE the LLM
# classification so a mis-triaged email can never slip through to a draft.
# Over-matching only ever routes an email to a human (fail-safe), never the
# other way, so the lists err on the side of catching more.
_EMERGENCY_RE = _kw(
    "chest pain",
    "difficulty breathing",
    "trouble breathing",
    "can't breathe",
    "cant breathe",
    "cannot breathe",
    "shortness of breath",
    "severe bleeding",
    "unconscious",
    "unresponsive",
    "suicid",
    "self-harm",
    "overdose",
    "stroke",
    "heart attack",
    "anaphyla",
    "seizure",
    "911",
    "112",
    "emergency",
)
_LEGAL_RE = _kw(
    "lawyer",
    "attorney",
    "solicitor",
    "lawsuit",
    "legal action",
    "take legal",
    "malpractice",
    "negligence",
    "subpoena",
    "litigation",
    "sue ",
)
_BILLING_DISPUTE_RE = _kw(
    "dispute",
    "overcharge",
    "over-charge",
    "wrong bill",
    "incorrect charge",
    "incorrectly charged",
    "double charged",
    "billed twice",
    "chargeback",
    "refund",
)

# --- Laboratory (requirement B) ---------------------------------------------
# Results must NEVER be drafted (fail-safe override, closes a real gap: today a
# mis-tagged "what were my results?" would slip through to ADMIN_DIRECT_REPLY
# if the LLM didn't happen to pick intent=test_results).
_LAB_RESULTS_RE = _kw(
    "my results",
    "my test results",
    "my lab results",
    "results are ready",
    "results are back",
    "results are available",
    "what were my results",
    "have my results",
    "receive my results",
    "biopsy results",
    "blood test results",
    "imaging results",
    "scan results",
    "x-ray results",
    "xray results",
)
# Lab appointment requests are booking actions — restrict to staff, never
# drafted, same as any other appointment (see _ROUTE_TO_STAFF_INTENTS), but
# tagged to the laboratory team specifically.
_LAB_APPOINTMENT_RE = _kw(
    "book a blood test",
    "book my blood test",
    "schedule a blood test",
    "schedule my blood test",
    "book a lab appointment",
    "schedule a lab appointment",
    "book my lab",
    "schedule my lab",
    "reschedule my blood test",
    "reschedule my lab",
    "change my lab appointment",
)
# Preparation questions ARE allowed to be drafted — this is annotation-only
# (see module docstring): it tags department without touching classification,
# so normal confidence/urgency/clinical-intent logic still applies unchanged.
_LAB_PREP_RE = _kw(
    "how do i prepare",
    "how should i prepare",
    "prepare for my",
    "prepare for the",
    "fasting",
    "fast for",
    "should i fast",
    "do i need to fast",
    "bring a sample",
    "urine sample",
    "stool sample",
    "before my blood test",
    "before my lab",
    "before my bloodwork",
)

# --- Gastroenterology (requirement B) ---------------------------------------
# Procedure bookings are restricted to staff, never drafted — same rationale as
# lab appointments, so a colonoscopy/gastroscopy booking is never treated the
# same as a routine admin question just because the LLM missed the intent.
_GASTRO_PROCEDURE_RE = _kw("colonoscopy", "gastroscopy", "endoscopy")
# General mentions are annotation-only: they narrow which team owns the routing
# outcome without changing whether it escalates (existing clinical/urgency
# checks still decide that, as they should for anything symptom-described).
# \bibs\b (word-boundary) avoids matching the substring inside unrelated words
# like "ribs"; the rest are safe as plain substrings (multi-word phrases).
_GASTRO_GENERAL_RE = re.compile(
    r"gastroenterolog|acid reflux|heartburn|irritable bowel|\bibs\b|stomach pain|abdominal pain",
    re.IGNORECASE,
)

# --- Physiotherapy (requirement B) ------------------------------------------
# Physio is booked directly by the physiotherapy team, not front office — this
# is a restriction (route to staff, never drafted) + annotation (which team),
# not a permission to auto-draft. Whether a referral was already given only
# changes the routing REASON (ready to book vs. needs a referral first), never
# the classification — an informational "you need a referral first" reply is
# something staff send (optionally using the "physio-referral-required"
# canned template via the /templates picker), not something the AI drafts
# unsupervised.
# \bphysio\b catches the standalone abbreviation ("book physio for my knee");
# it does NOT match inside "physiotherapy"/"physiotherapist" (no word boundary
# between "physio" and the following letter there), so both forms are listed.
_PHYSIO_RE = re.compile(r"physiotherapy|physiotherapist|\bphysio\b", re.IGNORECASE)
_PHYSIO_REFERRAL_EVIDENCE_RE = _kw(
    "referred me",
    "referral from",
    "already saw",
    "already had my ortho",
    "orthopaedic consult",
    "orthopedic consult",
    "ortho cleared me",
    "orthopaedist referred",
    "orthopedist referred",
    "cleared for physio",
)


def classify_review(triage: dict, *, text: str = "") -> SafetyDecision:
    """Return a :class:`SafetyDecision` for a triage result.

    ``triage`` is the dict produced by :meth:`TriageService.classify` (enum values
    are plain strings). ``text`` is the raw email (subject + body); when provided,
    deterministic keyword gates run first and take precedence over the LLM
    intent, so emergencies / legal / billing-dispute / domain-specific
    exclusions are caught even if the model mislabels the intent. Escalation
    triggers are checked in priority order so the reason names the most
    significant cause.
    """
    intent = str(triage.get("intent", ""))
    urgency = str(triage.get("urgency", ""))
    department = str(triage.get("department", ""))
    try:
        confidence = float(triage.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    # --- Deterministic keyword gates (highest priority, LLM-independent) ---
    if text:
        if _EMERGENCY_RE.search(text):
            return SafetyDecision(
                ReviewClassification.NEEDS_PHYSICIAN_REVIEW,
                "possible emergency detected in the message — routed to a clinician immediately.",
                department,
            )
        if _LEGAL_RE.search(text):
            return SafetyDecision(
                ReviewClassification.ROUTE_TO_STAFF,
                "legal matter detected — must be handled by staff, never AI-drafted.",
                department,
            )
        if _BILLING_DISPUTE_RE.search(text):
            return SafetyDecision(
                ReviewClassification.ROUTE_TO_STAFF,
                "billing dispute detected — must be handled by staff, never AI-drafted.",
                department,
            )
        if _LAB_RESULTS_RE.search(text):
            return SafetyDecision(
                ReviewClassification.NEEDS_PHYSICIAN_REVIEW,
                "lab/imaging results requested — must never be AI-drafted, routed to a clinician.",
                Department.laboratory.value,
            )
        if _LAB_APPOINTMENT_RE.search(text):
            return SafetyDecision(
                ReviewClassification.ROUTE_TO_STAFF,
                "laboratory appointment request — routed to lab scheduling staff, never AI-drafted.",
                Department.laboratory.value,
            )
        if _GASTRO_PROCEDURE_RE.search(text):
            return SafetyDecision(
                ReviewClassification.ROUTE_TO_STAFF,
                "gastroenterology procedure booking — routed to the gastroenterology team, never AI-drafted.",
                Department.gastroenterology.value,
            )
        if _PHYSIO_RE.search(text):
            if _PHYSIO_REFERRAL_EVIDENCE_RE.search(text):
                reason = (
                    "physiotherapy request with referral evidence — routed to the "
                    "physiotherapy team for direct booking, never AI-drafted."
                )
            else:
                reason = (
                    "physiotherapy request — an orthopaedic consult/referral is "
                    "required first; routed to the physiotherapy team (see the "
                    "'physio-referral-required' template), never AI-drafted."
                )
            return SafetyDecision(ReviewClassification.ROUTE_TO_STAFF, reason, Department.physiotherapy.value)

        # Annotation-only: narrow the department without changing the outcome
        # that the logic below would otherwise reach.
        if _LAB_PREP_RE.search(text):
            department = Department.laboratory.value
        elif _GASTRO_GENERAL_RE.search(text):
            department = Department.gastroenterology.value

    # --- Intent-based rules ---
    if intent == Intent.irrelevant.value:
        return SafetyDecision(
            ReviewClassification.IRRELEVANT,
            "email is irrelevant to the clinic — no reply needed.",
            department,
        )
    if intent in _CLINICAL_INTENTS:
        return SafetyDecision(
            ReviewClassification.NEEDS_PHYSICIAN_REVIEW,
            f"intent={intent} requires clinical interpretation — routed to a clinician.",
            department,
        )
    if intent in _ROUTE_TO_STAFF_INTENTS:
        return SafetyDecision(
            ReviewClassification.ROUTE_TO_STAFF,
            f"intent={intent} must be handled by staff directly — never AI-drafted.",
            department,
        )
    if department == Department.specialist.value:
        return SafetyDecision(
            ReviewClassification.NEEDS_PHYSICIAN_REVIEW,
            "specialist routing — a clinician must review before sending.",
            department,
        )
    if urgency in _ESCALATED_URGENCIES:
        return SafetyDecision(
            ReviewClassification.NEEDS_PHYSICIAN_REVIEW,
            f"urgency={urgency} — escalated for clinician review.",
            department,
        )
    if confidence < CONFIDENCE_THRESHOLD:
        return SafetyDecision(
            ReviewClassification.NEEDS_PHYSICIAN_REVIEW,
            f"confidence {confidence:.2f} below {CONFIDENCE_THRESHOLD:.2f} — "
            "escalated for human review (unclear or conflicting information).",
            department,
        )
    return SafetyDecision(
        ReviewClassification.ADMIN_DIRECT_REPLY,
        f"routine administrative request (intent={intent}, confidence {confidence:.2f}).",
        department,
    )
