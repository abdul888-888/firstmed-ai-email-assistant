"""Unit tests for the Healzz service foundation (Phase 10)."""

from __future__ import annotations

import httpx
import pytest
from app.core.config import settings
from app.services.healzz_service import (
    HealzzApiError,
    HealzzNotConfiguredError,
    HealzzService,
)


async def test_not_configured_by_default():
    svc = HealzzService()
    assert svc.configured is False
    status = await svc.get_status()
    assert status == {"configured": False, "base_url_set": False}


async def test_request_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "healzz_api_base_url", "")
    monkeypatch.setattr(settings, "healzz_api_key", "")
    with pytest.raises(HealzzNotConfiguredError):
        await HealzzService().ping()


async def test_ping_calls_health_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "healzz_api_base_url", "https://healzz.example/api/")
    monkeypatch.setattr(settings, "healzz_api_key", "secret-key")

    def handler(request: httpx.Request) -> httpx.Response:
        # Trailing slash trimmed; bearer auth attached.
        assert str(request.url) == "https://healzz.example/api/health"
        assert request.headers["authorization"] == "Bearer secret-key"
        return httpx.Response(200, json={"status": "ok"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await HealzzService(client=client).ping()
    await client.aclose()
    assert result == {"status": "ok"}


async def test_request_raises_on_error_status(monkeypatch):
    monkeypatch.setattr(settings, "healzz_api_base_url", "https://healzz.example")
    monkeypatch.setattr(settings, "healzz_api_key", "k")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(HealzzApiError):
        await HealzzService(client=client).ping()
    await client.aclose()


async def test_configured_status(monkeypatch):
    monkeypatch.setattr(settings, "healzz_api_base_url", "https://healzz.example")
    monkeypatch.setattr(settings, "healzz_api_key", "k")
    assert await HealzzService().get_status() == {"configured": True, "base_url_set": True}
