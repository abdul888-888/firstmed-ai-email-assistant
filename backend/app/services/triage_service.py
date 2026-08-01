"""AI triage: classify an inbound patient email (Phase 5).

Uses Claude with a constrained JSON schema so the result always maps onto the
``TriageResult`` shape (intent / urgency / department / summary / confidence).
"""

from __future__ import annotations

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
        return data