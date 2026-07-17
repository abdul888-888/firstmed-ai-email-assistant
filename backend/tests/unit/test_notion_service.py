"""Unit tests for the Notion service (mocked Notion API)."""

from __future__ import annotations

import httpx
import pytest
from app.core.config import settings
from app.services.notion_service import (
    NotionApiError,
    NotionNotConfiguredError,
    NotionService,
)


@pytest.fixture
def notion_configured(monkeypatch):
    monkeypatch.setattr(settings, "notion_api_key", "secret_test_token")


def _service(handler) -> NotionService:
    return NotionService(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_search_simplifies_results(notion_configured):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/search"
        assert request.headers["authorization"] == "Bearer secret_test_token"
        assert request.headers["notion-version"]
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "page-1",
                        "object": "page",
                        "url": "https://notion.so/page-1",
                        "last_edited_time": "2026-01-01T00:00:00.000Z",
                        "properties": {
                            "Name": {
                                "type": "title",
                                "title": [{"plain_text": "Triage SOP"}],
                            }
                        },
                    },
                    {
                        "id": "db-1",
                        "object": "database",
                        "url": "https://notion.so/db-1",
                        "title": [{"plain_text": "Templates"}],
                    },
                ],
                "has_more": False,
                "next_cursor": None,
            },
        )

    svc = _service(handler)
    data = await svc.search("sop", page_size=10)
    await svc._client.aclose()

    assert data["results"][0] == {
        "id": "page-1",
        "object": "page",
        "title": "Triage SOP",
        "url": "https://notion.so/page-1",
        "last_edited_time": "2026-01-01T00:00:00.000Z",
    }
    assert data["results"][1]["title"] == "Templates"
    assert data["has_more"] is False


async def test_get_page_content_extracts_text(notion_configured):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/blocks/page-1/children"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "b1",
                        "type": "paragraph",
                        "has_children": False,
                        "paragraph": {
                            "rich_text": [{"plain_text": "Hello "}, {"plain_text": "world"}]
                        },
                    },
                    {
                        "id": "b2",
                        "type": "heading_1",
                        "has_children": False,
                        "heading_1": {"rich_text": [{"plain_text": "Section"}]},
                    },
                ],
                "has_more": False,
                "next_cursor": None,
            },
        )

    svc = _service(handler)
    data = await svc.get_page_content("page-1")
    await svc._client.aclose()

    assert data["page_id"] == "page-1"
    assert data["blocks"][0]["text"] == "Hello world"
    assert data["blocks"][1]["text"] == "Section"


async def test_get_page_title(notion_configured):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/pages/page-9"
        return httpx.Response(
            200,
            json={
                "id": "page-9",
                "url": "https://notion.so/page-9",
                "created_time": "2026-01-01T00:00:00.000Z",
                "last_edited_time": "2026-02-01T00:00:00.000Z",
                "properties": {"Title": {"type": "title", "title": [{"plain_text": "FAQ"}]}},
            },
        )

    svc = _service(handler)
    data = await svc.get_page("page-9")
    await svc._client.aclose()

    assert data["title"] == "FAQ"
    assert data["url"] == "https://notion.so/page-9"


async def test_api_error_raises(notion_configured):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    svc = _service(handler)
    with pytest.raises(NotionApiError):
        await svc.search("x")
    await svc._client.aclose()


async def test_not_configured_raises():
    # No notion_api_key set (default empty).
    with pytest.raises(NotionNotConfiguredError):
        await NotionService().search("x")


async def test_connection_not_configured():
    data = await NotionService().get_connection()
    assert data == {"configured": False}
