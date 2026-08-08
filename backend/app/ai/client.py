"""Async AI client wrapper supporting multiple providers.

Supports Claude (Anthropic) and Groq via their native or OpenAI-compatible APIs.
Configured via ANTHROPIC_API_KEY or GROQ_API_KEY environment variables.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_CLAUDE_MODEL = "claude-3-5-sonnet-20241022"


class AIError(Exception):
    """Base class for AI client errors."""


class AINotConfiguredError(AIError):
    """No API key is configured for any supported provider."""


class AIClient:
    def __init__(self, *, api_key: str | None = None, model: str | None = None, provider: str | None = None) -> None:
        """Initialize AI client.
        
        Args:
            api_key: Explicit API key override. If not provided, reads from environment.
            model: Model name override. If not provided, reads from settings.
            provider: Provider hint: "anthropic", "groq", or "auto" (default).
                     If "auto", detects from api_key or model name.
        """
        self.model = model or getattr(settings, "ai_model", DEFAULT_CLAUDE_MODEL)
        
        # Determine provider from model name if not explicit
        if provider == "auto" or provider is None:
            if self.model.startswith("claude"):
                provider = "anthropic"
            elif self.model.startswith("llama") or self.model.startswith("mixtral"):
                provider = "groq"
            else:
                # Default to Anthropic for unknown models
                provider = "anthropic"
        
        self.provider = provider
        
        # Load API key based on provider
        if provider == "anthropic":
            self._api_key = (
                api_key
                if api_key is not None
                else os.getenv("ANTHROPIC_API_KEY") or getattr(settings, "anthropic_api_key", None)
            )
            if not self.model.startswith("claude"):
                self.model = DEFAULT_CLAUDE_MODEL
        elif provider == "groq":
            self._api_key = (
                api_key
                if api_key is not None
                else os.getenv("GROQ_API_KEY") or getattr(settings, "groq_api_key", None)
            )
            if not (self.model.startswith("llama") or self.model.startswith("mixtral")):
                self.model = DEFAULT_GROQ_MODEL
        else:
            raise AIError(f"Unsupported provider: {provider}")
            
        self._client: Any = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _ensure(self) -> Any:
        if not self.configured:
            raise AINotConfiguredError(
                f"{self.provider.upper()}_API_KEY is not configured in environment"
            )
        if self._client is None:
            if self.provider == "anthropic":
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=self._api_key)
            elif self.provider == "groq":
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self._api_key,
                    base_url="https://api.groq.com/openai/v1",
                )
        return self._client

    async def text(
        self, *, system: str, user: str, max_tokens: int | None = None, thinking: bool = True
    ) -> str:
        """Free-form completion."""
        client = self._ensure()
        try:
            if self.provider == "anthropic":
                resp = await client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens or getattr(settings, "ai_max_tokens", 4096),
                    system=system,
                    messages=[
                        {"role": "user", "content": user},
                    ],
                    temperature=0.3,
                )
                return resp.content[0].text
            else:  # groq
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
            raise AIError(f"{self.provider.capitalize()} request failed: {exc}") from exc

    async def structured(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Structured JSON completion."""
        client = self._ensure()
        json_instruction = (
            f"\n\nRespond strictly with valid JSON adhering to this schema:\n{json.dumps(schema)}"
        )
        try:
            if self.provider == "anthropic":
                resp = await client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens or getattr(settings, "ai_max_tokens", 4096),
                    system=system + json_instruction,
                    messages=[
                        {"role": "user", "content": user},
                    ],
                    temperature=0.1,
                )
                text = resp.content[0].text
            else:  # groq
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
            raise AIError(f"{self.provider.capitalize()} returned invalid JSON: {exc}") from exc
        except Exception as exc:
            raise AIError(f"{self.provider.capitalize()} structured request failed: {exc}") from exc


def get_ai_client() -> AIClient:
    """Default AI client - uses environment configuration."""
    return AIClient()