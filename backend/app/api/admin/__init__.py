"""Administration API — templates, workflows, users, config (Phases 7, 11-13)."""

from fastapi import APIRouter

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/status", summary="Module status")
async def status() -> dict:
    return {"module": "admin", "implemented": False, "phase": 7}
