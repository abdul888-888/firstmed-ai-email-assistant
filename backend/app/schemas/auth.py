"""Authentication schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    requires_2fa: bool = False
    challenge_id: str | None = None
    role: str | None = None
    redirect_url: str | None = None


class TwoFactorVerifyRequest(BaseModel):
    challenge_id: str
    code: str


class InviteSetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class TokenPayload(BaseModel):
    sub: str | None = None


class GoogleAuthorizationURL(BaseModel):
    """Where to send the browser to begin the Google OAuth consent flow."""

    authorization_url: str
    state: str

