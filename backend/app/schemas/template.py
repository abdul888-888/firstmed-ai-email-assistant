"""Schemas for canned-response templates (Phase 7)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TemplateCategory(str, enum.Enum):
    front_office = "front_office"
    billing = "billing"
    scheduling = "scheduling"
    clinical = "clinical"
    general = "general"


class TemplateRead(BaseModel):
    id: uuid.UUID
    key: str
    title: str
    category: str
    body: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TemplateList(BaseModel):
    templates: list[TemplateRead] = Field(default_factory=list)
    count: int = 0
