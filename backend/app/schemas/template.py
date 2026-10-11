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


class TemplateWrite(BaseModel):
    key: str = Field(min_length=3, max_length=128, pattern=r"^[a-z0-9-]+$")
    title: str = Field(min_length=3, max_length=256)
    category: TemplateCategory = TemplateCategory.general
    body: str = Field(min_length=10, max_length=20000)
    is_active: bool = True


class TemplateList(BaseModel):
    templates: list[TemplateRead] = Field(default_factory=list)
    count: int = 0
