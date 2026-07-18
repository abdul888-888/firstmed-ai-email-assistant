"""Data-access layer for :class:`~app.models.user.User`."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole


class UserRepository:
    """Encapsulates all user persistence operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        email: str,
        hashed_password: str | None = None,
        full_name: str = "",
        role: UserRole = UserRole.front_office,
    ) -> User:
        """Create a user. ``hashed_password`` is ``None`` for SSO-only accounts."""
        user = User(
            email=email.lower(),
            hashed_password=hashed_password,
            full_name=full_name,
            role=role,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def list_active(self) -> list[User]:
        """Active staff, for assignment/collaboration pickers."""
        result = await self.session.execute(
            select(User).where(User.is_active.is_(True)).order_by(User.full_name, User.email)
        )
        return list(result.scalars().all())
