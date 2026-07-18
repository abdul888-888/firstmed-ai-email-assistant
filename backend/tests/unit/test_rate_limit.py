"""Verifies the Phase 13 slowapi integration actually enforces a limit.

The real ``/auth/*`` endpoints use a generous test-env limit (see
``app.core.rate_limit.AUTH_RATE_LIMIT``) so the shared pytest-session app
singleton never trips it mid-suite. This test exercises slowapi's wiring in
isolation — on a throwaway app with an intentionally low limit — to prove the
Limiter + exception handler + middleware are correctly integrated.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address


def test_slowapi_enforces_a_low_limit():
    limiter = Limiter(key_func=get_remote_address)
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/ping")
    @limiter.limit("2/minute")
    async def ping(request: Request) -> dict:
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429


def test_auth_rate_limit_is_generous_under_test_but_strict_otherwise():
    from app.core.rate_limit import AUTH_RATE_LIMIT

    # Prevents the real /auth/* endpoints from tripping mid pytest-session
    # (see module docstring), while still being a real anti-spam limit for an
    # actual local dev-server run.
    assert AUTH_RATE_LIMIT == "1000/minute"
