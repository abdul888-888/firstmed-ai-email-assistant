"""Async Groq (OpenAI-compatible) client wrapper.

Exposes ``text`` and ``structured`` methods using Groq's high-speed Llama models.
Configured via GROQ_API_KEY environment variable.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class AIError(Exception):
    """Base class for AI client errors."""


class AINotConfiguredError(AIError):
    """No Groq API key is configured."""


class AIClient:
    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = (
            api_key
            if api_key is not None
            else os.getenv("GROQ_API_KEY") or getattr(settings, "groq_api_key", None)
        )
        self.model = model or getattr(settings, "ai_model", DEFAULT_GROQ_MODEL)
        if self.model.startswith("claude"):
            self.model = DEFAULT_GROQ_MODEL
            
        self._client: Any = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _ensure(self) -> Any:
        if not self.configured:
            raise AINotConfiguredError("GROQ_API_KEY is not configured in environment")
        if self._client is None:
            # Uses OpenAI's Async SDK configured for Groq
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url="https://api.groq.com/openai/v1",
            )
        return self._client

    async def text(
        self, *, system: str, user: str, max_tokens: int | None = None, thinking: bool = True
    ) -> str:
        """Free-form completion via Groq."""
        client = self._ensure()
        try:
            resp = await client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens or getattr(settings, "ai_max_tokens", 1024),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:
            raise AIError(f"Groq request failed: {exc}") from exc

    async def structured(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Structured JSON completion via Groq json_object mode."""
        client = self._ensure()
        json_instruction = (
            f"\n\nRespond strictly with valid JSON adhering to this schema:\n{json.dumps(schema)}"
        )
        try:
            resp = await client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens or getattr(settings, "ai_max_tokens", 1024),
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system + json_instruction},
                    {"role": "user", "content": user},
                ],
                temperature=0.1,
            )
            text = resp.choices[0].message.content or "{}"
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIError(f"Groq returned invalid JSON: {exc}") from exc
        except Exception as exc:
            raise AIError(f"Groq structured request failed: {exc}") from exc


def get_ai_client() -> AIClient:
    """Default AI client."""
    return AIClient()