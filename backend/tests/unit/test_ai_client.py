"""Unit tests for the Anthropic client wrapper (no network)."""

from __future__ import annotations

import pytest
from app.ai.client import AIClient, AIError, AINotConfiguredError


class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Resp:
    def __init__(self, content: list) -> None:
        self.content = content


class _Messages:
    def __init__(self, resp=None, exc=None) -> None:
        self._resp = resp
        self._exc = exc
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return self._resp


class _FakeSDK:
    def __init__(self, messages: _Messages) -> None:
        self.messages = messages


def _client_with(messages: _Messages, model: str = "claude-test") -> AIClient:
    ai = AIClient(api_key="test-key", model=model)
    ai._client = _FakeSDK(messages)  # bypass real SDK construction
    return ai


async def test_text_concatenates_text_blocks():
    msgs = _Messages(resp=_Resp([_Block("Hello "), _Block("world")]))
    # Adaptive thinking is only requested on models that support it (Claude 4.6+).
    ai = _client_with(msgs, model="claude-opus-4-8")
    out = await ai.text(system="s", user="u")
    assert out == "Hello world"
    assert msgs.calls[0]["thinking"] == {"type": "adaptive"}


async def test_text_omits_thinking_on_unsupported_model():
    # Haiku 4.5 rejects adaptive thinking with a 400 — the client must omit it
    # (regression guard for the draft-endpoint 502).
    msgs = _Messages(resp=_Resp([_Block("hi")]))
    ai = _client_with(msgs, model="claude-haiku-4-5")
    await ai.text(system="s", user="u")
    assert "thinking" not in msgs.calls[0]


async def test_structured_parses_json():
    ai = _client_with(_Messages(resp=_Resp([_Block('{"intent": "billing_insurance"}')])))
    out = await ai.structured(system="s", user="u", schema={"type": "object"})
    assert out == {"intent": "billing_insurance"}


async def test_structured_rejects_non_json():
    ai = _client_with(_Messages(resp=_Resp([_Block("not json")])))
    with pytest.raises(AIError):
        await ai.structured(system="s", user="u", schema={})


async def test_api_error_is_normalized():
    ai = _client_with(_Messages(exc=RuntimeError("boom")))
    with pytest.raises(AIError):
        await ai.text(system="s", user="u")


async def test_not_configured_raises():
    ai = AIClient(api_key="")
    assert ai.configured is False
    with pytest.raises(AINotConfiguredError):
        await ai.text(system="s", user="u")
