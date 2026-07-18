"""Healzz integration API (Phase 10 foundation).

Reports configuration/connectivity. Concrete endpoints (appointments,
availability) build on ``HealzzService`` in later work.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.services.healzz_service import HealzzService

router = APIRouter(prefix="/healzz", tags=["healzz"])


@router.get("/status", summary="Module status")
async def status_() -> dict:
    state = await HealzzService().get_status()
    return {
        "module": "healzz",
        "phase": 10,
        "foundation": True,
        "configured": state["configured"],
    }
