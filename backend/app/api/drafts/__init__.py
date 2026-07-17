"""Draft generation & review API (implemented in Phases 8-9)."""

from fastapi import APIRouter

router = APIRouter(prefix="/drafts", tags=["drafts"])


@router.get("/status", summary="Module status")
async def status() -> dict:
    return {"module": "drafts", "implemented": False, "phase": 8}
