"""Data-access layer for :class:`~app.models.template.Template`."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import Template


class TemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, template_id: uuid.UUID) -> Template | None:
        return await self.session.get(Template, template_id)

    async def get_by_key(self, key: str) -> Template | None:
        result = await self.session.execute(select(Template).where(Template.key == key))
        return result.scalar_one_or_none()

    async def list(
        self, *, category: str | None = None, active_only: bool = True
    ) -> list[Template]:
        stmt = select(Template)
        if active_only:
            stmt = stmt.where(Template.is_active.is_(True))
        if category:
            stmt = stmt.where(Template.category == category)
        stmt = stmt.order_by(Template.category, Template.title)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(
        self,
        *,
        key: str,
        title: str,
        category: str,
        body: str,
        is_active: bool = True,
    ) -> Template:
        """Create or update the template identified by ``key``."""
        tpl = await self.get_by_key(key)
        if tpl is None:
            tpl = Template(key=key)
            self.session.add(tpl)
        tpl.title = title
        tpl.category = category
        tpl.body = body
        tpl.is_active = is_active
        await self.session.commit()
        await self.session.refresh(tpl)
        return tpl
