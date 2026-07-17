"""Async SQLAlchemy engine / session management.

Provides the async engine, a session factory, and the ``get_db`` FastAPI
dependency. SQLite (used by the test suite) is configured with a static pool so
an in-memory database is shared across connections.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.config import settings


def _engine_kwargs(url: str) -> dict[str, Any]:
    if url.startswith("sqlite"):
        return {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    return {"pool_pre_ping": True}


def create_engine(url: str | None = None) -> AsyncEngine:
    """Create an async engine for ``url`` (defaults to the configured DB)."""
    target = url or settings.sqlalchemy_database_uri
    return create_async_engine(
        target,
        echo=False,
        future=True,
        **_engine_kwargs(target),
    )


engine: AsyncEngine = create_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a database session."""
    async with AsyncSessionLocal() as session:
        yield session
