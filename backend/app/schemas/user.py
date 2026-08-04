"""User-related Pydantic schemas (request/response contracts)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = ""
    role: UserRole = UserRole.FRONT_OFFICE
    department: str = "FRONT_OFFICE"
    is_on_shift: bool = True


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: UserRole | None = None
    department: str | None = None
    is_active: bool | None = None
    is_on_shift: bool | None = None


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_active: bool
    shift_started_at: str | None = None
    created_at: datetime
    updated_at: datetime


class UserList(BaseModel):
    users: list[UserRead] = Field(default_factory=list)
    count: int = 0
