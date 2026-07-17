"""Healzz integration API (implemented in Phase 10)."""

from fastapi import APIRouter

router = APIRouter(prefix="/healzz", tags=["healzz"])


@router.get("/status", summary="Module status")
async def status() -> dict:
    return {"module": "healzz", "implemented": False, "phase": 10}
