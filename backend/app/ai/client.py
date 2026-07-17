"""Async Anthropic (Claude) client wrapper (Phase 5).

Thin adapter over the official ``anthropic`` SDK exposing two calls the services
need: ``text`` (free-form generation, adaptive thinking) and ``structured``
(JSON constrained by a schema via ``output_config.format``). Services depend on
this interface, so tests inject a fake and never touch the network.

Model defaults to ``settings.ai_model`` (``claude-haiku-4-5``).
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Substrings identifying models that support adaptive thinking (Claude 4.6+).
# Haiku 4.5 and older models reject ``thinking={"type": "adaptive"}`` with a 400,
# so we omit the parameter for them rather than crash the draft endpoint (502).
_ADAPTIVE_THINKING_MODELS = (
    "opus-4-6",
    "opus-4-7",
    "opus-4-8",
    "sonnet-4-6",
    "sonnet-5",
    "fable-5",
    "mythos-5",
)


class AIError(Exception):
    """Base class for AI client errors."""


class AINotConfiguredError(AIError):
    """No Anthropic API key is configured."""


class AIClient:
    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key if api_key is not None else settings.anthropic_api_key
        self.model = model or settings.ai_model
        self._client: Any = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    @property
    def supports_adaptive_thinking(self) -> bool:
        """True when the configured model accepts ``thinking={"type": "adaptive"}``."""
        return any(marker in self.model for marker in _ADAPTIVE_THINKING_MODELS)

    def _ensure(self) -> Any:
        if not self.configured:
            raise AINotConfiguredError("Anthropic API key is not configured")
        if self._client is None:
            # Imported lazily so the app boots even if the SDK is absent.
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    @staticmethod
    def _text_from(content: list[Any]) -> str:
        return "".join(block.text for block in content if getattr(block, "type", None) == "text")

    async def text(
        self, *, system: str, user: str, max_tokens: int | None = None, thinking: bool = True
    ) -> str:
        """Free-form completion. Adaptive thinking on by default for nuanced output.

        Adaptive thinking is only sent when the configured model supports it
        (Claude 4.6+); on models like Haiku 4.5 it is silently skipped so the
        request succeeds instead of erroring with a 400 (surfaced as a 502).
        """
        client = self._ensure()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or settings.ai_max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if thinking and self.supports_adaptive_thinking:
            kwargs["thinking"] = {"type": "adaptive"}
        try:
            resp = await client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - normalize any SDK/API error
            raise AIError(f"Claude request failed: {exc}") from exc
        return self._text_from(resp.content)

    async def structured(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Completion constrained to ``schema`` via output_config.format; returns parsed JSON."""
        client = self._ensure()
        try:
            resp = await client.messages.create(
                model=self.model,
                max_tokens=max_tokens or settings.ai_max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
        except Exception as exc:  # noqa: BLE001 - normalize any SDK/API error
            raise AIError(f"Claude structured request failed: {exc}") from exc

        text = self._text_from(resp.content)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIError(f"Claude returned non-JSON output: {exc}") from exc


def get_ai_client() -> AIClient:
    """Default AI client from settings."""
    return AIClient()
