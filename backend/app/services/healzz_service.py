"""Healzz integration foundation (Phase 10).

Async ``httpx`` wrapper for the external Healzz API, gated on
``settings.healzz_configured`` (base URL + API key). This lays the wiring —
config, auth headers, request/error normalization, and a status probe — that the
concrete Healzz endpoints (appointments, availability, etc.) will build on. It
never blocks app startup: unconfigured ⇒ callers get a clear error, not a crash.
"""

from __future__ import annotations

import httpx

from app.core.config import settings

_HTTP_TIMEOUT = 15.0


class HealzzError(Exception):
    """Base class for Healzz service errors."""


class HealzzNotConfiguredError(HealzzError):
    """No Healzz base URL / API key is configured."""


class HealzzApiError(HealzzError):
    """The Healzz API returned an error response."""


class HealzzService:
    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @property
    def configured(self) -> bool:
        return settings.healzz_configured

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.healzz_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

    async def get_status(self) -> dict:
        """Report configuration state without calling the API (safe when unset)."""
        return {
            "configured": self.configured,
            "base_url_set": bool(settings.healzz_api_base_url),
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """Perform an authenticated request against the Healzz API.

        Foundation helper for the concrete endpoints added later; raises
        ``HealzzNotConfiguredError`` when credentials are missing and
        ``HealzzApiError`` on transport / non-2xx responses.
        """
        if not self.configured:
            raise HealzzNotConfiguredError("Healzz integration is not configured")

        url = f"{settings.healzz_api_base_url.rstrip('/')}{path}"

        async def _do(client: httpx.AsyncClient) -> httpx.Response:
            try:
                return await client.request(
                    method, url, headers=self._headers(), json=json, params=params
                )
            except httpx.HTTPError as exc:
                raise HealzzApiError(f"Healzz request failed: {exc}") from exc

        if self._client is not None:
            resp = await _do(self._client)
        else:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await _do(client)

        if resp.status_code >= httpx.codes.BAD_REQUEST:
            raise HealzzApiError(f"Healzz API {resp.status_code}: {resp.text}")
        return resp.json()

    async def ping(self) -> dict:
        """Lightweight connectivity probe (GET /health). Example concrete call."""
        return await self._request("GET", "/health")
