"""User model and role enumeration."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Enum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    """Staff roles, mirroring the PRD 'User Roles' section."""

    ADMIN = "admin"
    FRONT_OFFICE = "front_office"
    PHYSIOTHERAPY = "physiotherapy"
    GASTROENTEROLOGY = "gastroenterology"
    LABORATORY = "laboratory"
    NURSE_SPECIALIST = "nurse_specialist"

    # Backward compatibility aliases
    admin = "admin"
    front_office = "front_office"
    nurse = "nurse_specialist"
    specialist = "physiotherapy"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    # Nullable: users created via Google SSO have no local password.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False),
        default=UserRole.FRONT_OFFICE,
        nullable=False,
    )
    department: Mapped[str] = mapped_column(String(50), default="FRONT_OFFICE", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_on_shift: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    shift_started_at: Mapped[str | None] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User id={self.id} email={self.email!r} role={self.role.value}>"
