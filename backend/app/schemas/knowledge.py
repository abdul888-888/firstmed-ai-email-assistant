"""Schemas for FirstMed's internally managed knowledge base."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.search import DocumentRead


class KnowledgeEntryWrite(BaseModel):
    title: str = Field(min_length=3, max_length=1024)
    content: str = Field(min_length=10, max_length=20000)
    category: str = Field(default="general", min_length=2, max_length=64)


class KnowledgeEntryList(BaseModel):
    entries: list[DocumentRead] = Field(default_factory=list)
    count: int = 0
