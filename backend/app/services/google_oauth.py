"""Google OAuth 2.0 helpers (authorization-code flow) for staff SSO + Gmail.

Talks to Google's OAuth endpoints directly over HTTPS with ``httpx`` so the flow
stays fully async and dependency-light. The ID token returned by the token
endpoint is decoded *without* signature verification: it is received directly
from Google over a server-to-server TLS channel, which Google documents as a
trusted source, so re-verifying its signature is unnecessary.

CSRF for the browser round-trip is handled with a short-lived signed ``state``
JWT (stateless — no server session needed).
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import settings

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"  # noqa: S105 - public endpoint URL

_STATE_TYPE = "oauth_state"
_STATE_TTL_SECONDS = 600
_HTTP_TIMEOUT = 10.0


class GoogleOAuthError(Exception):
    """Raised when a Google OAuth exchange/refresh fails."""


@dataclass(slots=True)
class GoogleTokens:
    access_token: str
    expires_in: int
    scope: str
    refresh_token: str | None = None
    id_token: str | None = None

    @property
    def expiry(self) -> dt.datetime:
        return dt.datetime.now(dt.UTC) + dt.timedelta(seconds=self.expires_in)


@dataclass(slots=True)
class GoogleProfile:
    sub: str
    email: str
    name: str = ""
    email_verified: bool = False


# --- CSRF state -----------------------------------------------------------


def make_state() -> str:
    """Return a signed, short-lived state token for the OAuth round-trip."""
    now = dt.datetime.now(dt.UTC)
    payload = {
        "type": _STATE_TYPE,
        "nonce": str(uuid.uuid4()),
        "iat": now,
        "exp": now + dt.timedelta(seconds=_STATE_TTL_SECONDS),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def verify_state(state: str) -> bool:
    """Validate a state token produced by :func:`make_state`."""
    try:
        payload = jwt.decode(state, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.PyJWTError:
        return False
    return payload.get("type") == _STATE_TYPE


# --- Authorization URL ----------------------------------------------------


def build_authorization_url(state: str) -> str:
    """Build the Google consent-screen URL to redirect the browser to."""
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(settings.google_oauth_scopes),
        "state": state,
        # offline + consent => we receive a refresh token.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{AUTH_URI}?{urlencode(params)}"


# --- Token endpoint -------------------------------------------------------


def _parse_tokens(data: dict) -> GoogleTokens:
    return GoogleTokens(
        access_token=data["access_token"],
        expires_in=int(data.get("expires_in", 0)),
        scope=data.get("scope", ""),
        refresh_token=data.get("refresh_token"),
        id_token=data.get("id_token"),
    )


async def exchange_code(code: str, *, client: httpx.AsyncClient | None = None) -> GoogleTokens:
    """Exchange an authorization ``code`` for tokens."""
    payload = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    return await _post_token(payload, client=client)


async def refresh_access_token(
    refresh_token: str, *, client: httpx.AsyncClient | None = None
) -> GoogleTokens:
    """Obtain a fresh access token from a stored refresh token."""
    payload = {
        "refresh_token": refresh_token,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "grant_type": "refresh_token",
    }
    return await _post_token(payload, client=client)


async def _post_token(payload: dict, *, client: httpx.AsyncClient | None = None) -> GoogleTokens:
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=_HTTP_TIMEOUT)
    try:
        resp = await client.post(TOKEN_URI, data=payload)
    except httpx.HTTPError as exc:
        raise GoogleOAuthError(f"token request failed: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()

    if resp.status_code != httpx.codes.OK:
        raise GoogleOAuthError(f"token endpoint returned {resp.status_code}: {resp.text}")
    return _parse_tokens(resp.json())


def decode_id_token(id_token: str) -> GoogleProfile:
    """Decode the OIDC ID token (already trusted — see module docstring)."""
    try:
        claims = jwt.decode(id_token, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise GoogleOAuthError(f"malformed id_token: {exc}") from exc

    email = claims.get("email")
    sub = claims.get("sub")
    if not email or not sub:
        raise GoogleOAuthError("id_token missing email/sub claim")
    return GoogleProfile(
        sub=str(sub),
        email=str(email),
        name=str(claims.get("name", "")),
        email_verified=bool(claims.get("email_verified", False)),
    )
