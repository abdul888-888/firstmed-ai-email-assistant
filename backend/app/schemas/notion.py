"""Notion API response schemas (Phase 3).

The Notion API returns large, deeply-nested objects; these schemas expose the
fields the assistant actually needs, with raw ``properties`` passed through for
callers that want more.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NotionConnection(BaseModel):
    """Whether the Notion integration is configured (and, if so, who it is)."""

    configured: bool
    bot_name: str | None = None
    workspace_name: str | None = None


class NotionItem(BaseModel):
    """A simplified page or database from a search / query result.

    ``properties`` / ``content`` are populated for database *rows* (from
    ``query_database``): a readable name→value map and a flattened text block of
    the row's fields, so pricing/insurance tables become retrievable content.
    """

    id: str
    object: str = ""
    title: str = ""
    url: str = ""
    last_edited_time: str = ""
    properties: dict[str, str] = Field(default_factory=dict)
    content: str = ""


class NotionSearchResults(BaseModel):
    results: list[NotionItem] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False


class NotionPage(BaseModel):
    id: str
    url: str = ""
    title: str = ""
    created_time: str = ""
    last_edited_time: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class NotionBlock(BaseModel):
    id: str
    type: str = ""
    text: str = ""
    has_children: bool = False


class NotionPageContent(BaseModel):
    page_id: str
    blocks: list[NotionBlock] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False
