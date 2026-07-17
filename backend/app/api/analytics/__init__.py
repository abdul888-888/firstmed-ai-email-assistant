"""Analytics & reporting API (implemented in Phase 12)."""

from fastapi import APIRouter

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/status", summary="Module status")
async def status() -> dict:
    return {"module": "analytics", "implemented": False, "phase": 12}
