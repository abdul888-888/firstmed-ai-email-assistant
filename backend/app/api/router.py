"""Aggregate API router mounted under the versioned prefix.

Placeholder module routers (gmail, notion, healzz, drafts, workflows, analytics,
admin) are included now so the API surface mirrors the target architecture and
is filled in during later phases.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import (
    admin,
    ai,
    analytics,
    drafts,
    email,
    gmail,
    healzz,
    notion,
    reviews,
    search,
    templates,
    workflows,
)
from app.api import health as health_module
from app.api.auth import routes as auth_routes

api_router = APIRouter()

# Active in Phase 1
api_router.include_router(health_module.router)
api_router.include_router(auth_routes.router)

# Implemented integrations
api_router.include_router(email.router)
api_router.include_router(gmail.router)
api_router.include_router(notion.router)
api_router.include_router(search.router)
api_router.include_router(ai.router)
api_router.include_router(healzz.router)
api_router.include_router(drafts.router)
api_router.include_router(workflows.router)
api_router.include_router(reviews.router)
api_router.include_router(templates.router)
api_router.include_router(analytics.router)
api_router.include_router(admin.router)
