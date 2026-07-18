"""slowapi rate limiting for public, pre-auth endpoints (local hardening, Phase 13).

Scoped to the unauthenticated ``/auth`` endpoints (register, login, Google
OAuth start/callback) — the classic pre-auth targets for local spamming
(registration spam, login brute-forcing). Authenticated endpoints already
require a valid bearer token, which is a much stronger gate.

The limit is generous in ``test`` specifically: the test suite imports the
FastAPI ``app`` singleton once per pytest session (see ``tests/conftest.py``),
and slowapi's default in-memory store keys by client IP — which collapses to
the same value for every request made through httpx's ``ASGITransport``. A
strict limit would eventually 429 unrelated tests that happen to hit these
endpoints many times across the session. A real, low limit only matters when
someone is actually running the local dev server.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(key_func=get_remote_address)

# Effectively unlimited under pytest; a real anti-spam limit otherwise.
AUTH_RATE_LIMIT = "1000/minute" if settings.environment == "test" else "10/minute"
