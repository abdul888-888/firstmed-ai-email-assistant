"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.schemas.health import HealthStatus, ReadinessStatus

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health", response_model=HealthStatus, summary="Liveness probe")
async def health() -> HealthStatus:
    """Fast liveness check — never touches external dependencies."""
    return HealthStatus(
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )


async def _check_database(session: AsyncSession) -> bool:
    try:
        await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 - report, never crash the probe
        logger.warning("readiness.database_error", error=str(exc))
        return False


async def _check_redis() -> bool:
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_uri, socket_connect_timeout=2)
        try:
            return bool(await client.ping())
        finally:
            await client.aclose()
    except Exception as exc:  # noqa: BLE001 - report, never crash the probe
        logger.warning("readiness.redis_error", error=str(exc))
        return False


@router.get(
    "/health/ready",
    response_model=ReadinessStatus,
    summary="Readiness probe (checks DB + Redis)",
)
async def readiness(session: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Readiness check — verifies the database and Redis are reachable."""
    db_ok = await _check_database(session)
    redis_ok = await _check_redis()
    checks = {
        "database": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }
    all_ok = db_ok and redis_ok
    payload = ReadinessStatus(status="ready" if all_ok else "not_ready", checks=checks)
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content=payload.model_dump(),
    )
