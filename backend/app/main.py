"""FastAPI application entrypoint.

uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import limiter
from app.middleware.request_id import RequestIDMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    logger.info(
        "app.startup",
        app=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )
    yield
    logger.info("app.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Human-in-the-loop AI administrative email assistant for FirstMed. "
            "Prepares Gmail drafts for routine inquiries; never sends automatically."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS
    cors_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://firstmed-ai-email-assistant.vercel.app",
    ]
    if isinstance(settings.backend_cors_origins, list):
        cors_origins.extend([str(o) for o in settings.backend_cors_origins if str(o) not in cors_origins])
    elif isinstance(settings.backend_cors_origins, str) and settings.backend_cors_origins:
        if settings.backend_cors_origins not in cors_origins:
            cors_origins.append(settings.backend_cors_origins)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # Request correlation
    app.add_middleware(RequestIDMiddleware)

    # Rate limiting (Phase 13, local hardening) — see app.core.rate_limit.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # Routes
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    return app


app = create_app()
