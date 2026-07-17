"""Retrieval / search schemas (Phase 4)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    source_id: str
    title: str
    content: str
    url: str | None = None
    doc_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class SearchHit(BaseModel):
    score: float
    document: DocumentRead


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[SearchHit] = Field(default_factory=list)


class ReindexResult(BaseModel):
    gmail_indexed: int
    notion_indexed: int
    notes: list[str] = Field(default_factory=list)


class IndexStats(BaseModel):
    total: int = 0
    gmail: int = 0
    notion: int = 0
