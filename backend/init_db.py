#!/usr/bin/env python
"""Initialize the database by creating all tables from models."""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings
from app.models.base import Base

async def init_db():
    """Create all database tables."""
    print("🔄 Initializing database...")
    print(f"Database URL: {settings.sqlalchemy_database_uri}")

    engine = create_async_engine(
        settings.sqlalchemy_database_uri,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()
    print("✅ Database initialized! All tables created.")

if __name__ == "__main__":
    asyncio.run(init_db())
