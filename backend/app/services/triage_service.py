"""AI triage: classify an inbound patient email (Phase 5).

Uses Claude with a constrained JSON schema so the result always maps onto the
``TriageResult`` shape (intent / urgency / department / summary / confidence).
"""

from __future__ import annotations

import re
from typing import Any

from app.ai.client import AIClient, get_ai_client
from app.ai.prompts import TRIAGE_SYSTEM, build_triage_user
from app.schemas.ai import Department, Intent, Urgency



# JSON schema for output_config.format — enums keep the model on-vocabulary.
TRIAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": [e.value for e in Intent]},
        "urgency": {"type": "string", "enum": [e.value for e in Urgency]},
        "department": {"type": "string", "enum": [e.value for e in Department]},
        "summary": {"type": "string"},
        "requires_human_review": {"type": "boolean"},
        "confidence": {"type": "number"},
    },
    "required": [
        "intent",
        "urgency",
        "department",
        "summary",
        "requires_human_review",
        "confidence",
    ],
    "additionalProperties": False,
}

_TRIAGE_MAX_TOKENS = 1024

# Narrow, deterministic labels for routine front-office questions. This never
# supplies an answer: the workflow still needs an approved template or verified
# knowledge-base match before it creates a draft.
_UNSAFE_ADMIN_CONTEXT = re.compile(
    r"\b(book|booking|schedule|reschedule|cancel|cancellation|change my appointment|"
    r"result|symptom|pain|diagnos|treatment|medication|prescription|emergency|complaint|"
    r"refund|overcharg|dispute|legal)\b",
    re.IGNORECASE,
)
_ADMIN_PATTERNS: tuple[tuple[Intent, re.Pattern[str]], ...] = (
    (Intent.pricing, re.compile(r"\b(price|pricing|cost|fee|how much)\b", re.IGNORECASE)),
    (Intent.parking, re.compile(r"\b(parking|park|validation)\b", re.IGNORECASE)),
    (
        Intent.opening_hours,
        re.compile(
            r"\b(clinic hours|office hours|opening hours|operating hours|working hours|"
            r"opening time|closing time|what hours|hours are you open|when (?:do|are) you open|"
            r"when (?:do|are) you close)\b",
            re.IGNORECASE,
        ),
    ),
    (Intent.contact_information, re.compile(r"\b(phone number|telephone|contact details|email address|location|directions|address)\b", re.IGNORECASE)),
    (Intent.preparation_instructions, re.compile(r"\b(prepare|preparation|fasting|fast before|what should i bring)\b", re.IGNORECASE)),
    (Intent.service_information, re.compile(r"\b(do you offer|do you provide|is .+ available|availability of|have .+ service)\b", re.IGNORECASE)),
)


def _clear_administrative_intent(subject: str, body: str) -> Intent | None:
    """Recognise unambiguous, non-clinical administrative requests only."""
    text = f"{subject}\n{body}"
    if _UNSAFE_ADMIN_CONTEXT.search(text):
        return None
    for intent, pattern in _ADMIN_PATTERNS:
        if pattern.search(text):
            return intent
    return None


class TriageService:
    def __init__(self, ai: AIClient | None = None) -> None:
        self.ai = ai or get_ai_client()

    async def classify(self, subject: str, body: str) -> dict:
        try:
            data = await self.ai.structured(
                system=TRIAGE_SYSTEM,
                user=build_triage_user(subject, body),
                schema=TRIAGE_SCHEMA,
                max_tokens=_TRIAGE_MAX_TOKENS,
            )
        except Exception as e:
            # Fallback when Anthropic API fails (out of tokens / key unconfigured)
            # This allows the email ingestion pipeline to succeed safely.
            data = {
                "intent": Intent.GENERAL_INQUIRY.value if hasattr(Intent, "GENERAL_INQUIRY") else "general_inquiry",
                "urgency": Urgency.ROUTINE.value if hasattr(Urgency, "ROUTINE") else "routine",
                "department": Department.FRONT_OFFICE.value if hasattr(Department, "FRONT_OFFICE") else "front_office",
                "summary": f"Imported email: {subject[:100]}",
                "requires_human_review": True,
                "confidence": 0.5,
            }

        # Normalize: clamp confidence and force the human-review guardrail on.
        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        data["confidence"] = min(1.0, max(0.0, confidence))
        data["requires_human_review"] = True
        admin_intent = _clear_administrative_intent(subject, body)
        if admin_intent is not None:
            data["intent"] = admin_intent.value
            data["department"] = Department.front_office.value
            data["confidence"] = max(data["confidence"], 0.85)
        return data
