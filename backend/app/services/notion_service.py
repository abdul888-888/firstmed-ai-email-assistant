"""Read access to the FirstMed Notion knowledge base (Phase 3).

Wraps the Notion REST API with ``httpx`` (async), using a server-side internal
integration token (``NOTION_API_KEY``). Read-only: search pages/databases,
retrieve a page, and read a page's text blocks. This content feeds retrieval /
templates in later phases.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings

NOTION_BASE = "https://api.notion.com/v1"
_HTTP_TIMEOUT = 15.0


class NotionError(Exception):
    """Base class for Notion service errors."""


class NotionNotConfiguredError(NotionError):
    """No Notion integration token is configured."""


class NotionApiError(NotionError):
    """The Notion API returned an error response."""


def _plain_text(rich_text: list[dict] | None) -> str:
    if not rich_text:
        return ""
    return "".join(part.get("plain_text", "") for part in rich_text)


def _title_of(obj: dict) -> str:
    """Best-effort human title for a page or database object."""
    # Database objects carry a top-level ``title`` rich-text array.
    if obj.get("object") == "database":
        return _plain_text(obj.get("title"))
    # Page objects carry the title inside the property of type "title".
    for prop in (obj.get("properties") or {}).values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            return _plain_text(prop.get("title"))
    return ""


def _block_text(block: dict) -> str:
    block_type = block.get("type", "")
    content = block.get(block_type, {}) if block_type else {}
    if isinstance(content, dict):
        if "rich_text" in content:
            return _plain_text(content.get("rich_text"))
        if "title" in content:  # e.g. child_page
            title = content.get("title")
            return title if isinstance(title, str) else _plain_text(title)
    return ""


class NotionService:
    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.notion_api_key.get_secret_value()}",
            "Notion-Version": settings.notion_version,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        if not settings.notion_configured:
            raise NotionNotConfiguredError("Notion integration is not configured")

        async def _do(client: httpx.AsyncClient) -> httpx.Response:
            try:
                return await client.request(
                    method,
                    f"{NOTION_BASE}{path}",
                    headers=self._headers(),
                    json=json,
                    params=params,
                )
            except httpx.HTTPError as exc:
                raise NotionApiError(f"Notion request failed: {exc}") from exc

        if self._client is not None:
            resp = await _do(self._client)
        else:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await _do(client)

        if resp.status_code != httpx.codes.OK:
            raise NotionApiError(f"Notion API {resp.status_code}: {resp.text}")
        return resp.json()

    # --- public API -------------------------------------------------------

    async def get_connection(self) -> dict:
        if not settings.notion_configured:
            return {"configured": False}
        me = await self._request("GET", "/users/me")
        bot = me.get("bot", {}) or {}
        workspace = bot.get("workspace_name") if isinstance(bot, dict) else None
        return {
            "configured": True,
            "bot_name": me.get("name"),
            "workspace_name": workspace,
        }

    async def search(self, query: str | None = None, *, page_size: int = 25) -> dict:
        body: dict[str, Any] = {"page_size": page_size}
        if query:
            body["query"] = query
        data = await self._request("POST", "/search", json=body)
        results = [
            {
                "id": item.get("id", ""),
                "object": item.get("object", ""),
                "title": _title_of(item),
                "url": item.get("url", ""),
                "last_edited_time": item.get("last_edited_time", ""),
            }
            for item in data.get("results", [])
        ]
        return {
            "results": results,
            "next_cursor": data.get("next_cursor"),
            "has_more": bool(data.get("has_more", False)),
        }

    async def get_page(self, page_id: str) -> dict:
        data = await self._request("GET", f"/pages/{page_id}")
        return {
            "id": data.get("id", page_id),
            "url": data.get("url", ""),
            "title": _title_of(data),
            "created_time": data.get("created_time", ""),
            "last_edited_time": data.get("last_edited_time", ""),
            "properties": data.get("properties", {}),
        }

    async def get_page_content(self, page_id: str, *, page_size: int = 50) -> dict:
        data = await self._request(
            "GET", f"/blocks/{page_id}/children", params={"page_size": page_size}
        )
        blocks = [
            {
                "id": block.get("id", ""),
                "type": block.get("type", ""),
                "text": _block_text(block),
                "has_children": bool(block.get("has_children", False)),
            }
            for block in data.get("results", [])
        ]
        return {
            "page_id": page_id,
            "blocks": blocks,
            "next_cursor": data.get("next_cursor"),
            "has_more": bool(data.get("has_more", False)),
        }

    async def query_database(self, database_id: str, *, page_size: int = 25) -> dict:
        data = await self._request(
            "POST", f"/databases/{database_id}/query", json={"page_size": page_size}
        )
        results = [
            {
                "id": item.get("id", ""),
                "object": item.get("object", ""),
                "title": _title_of(item),
                "url": item.get("url", ""),
                "last_edited_time": item.get("last_edited_time", ""),
            }
            for item in data.get("results", [])
        ]
        return {
            "results": results,
            "next_cursor": data.get("next_cursor"),
            "has_more": bool(data.get("has_more", False)),
        }
