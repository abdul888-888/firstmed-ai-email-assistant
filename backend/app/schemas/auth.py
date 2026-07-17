"""Authentication schemas."""

from __future__ import annotations

from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str | None = None


class GoogleAuthorizationURL(BaseModel):
    """Where to send the browser to begin the Google OAuth consent flow."""

    authorization_url: str
    state: str
