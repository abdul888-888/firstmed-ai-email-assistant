"""Microsoft Graph OAuth 2.0 flow for Outlook/Microsoft 365 integration.

Implements the authorization-code flow per RFC 6749:
https://docs.microsoft.com/en-us/graph/auth-v2-user
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


class OutlookOAuthError(Exception):
    """Raised when OAuth flow fails."""

    pass


@dataclass
class OutlookTokens:
    """Access token response from Azure Entra ID."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    scope: str = ""
    expiry: datetime | None = None

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> OutlookTokens:
        """Parse token response from Azure Entra ID."""
        access_token = data.get("access_token")
        if not access_token:
            raise OutlookOAuthError("Missing access_token in response")

        # expires_in is in seconds
        expires_in = data.get("expires_in", 3600)
        expiry = datetime.utcnow() + timedelta(seconds=expires_in)

        return cls(
            access_token=access_token,
            refresh_token=data.get("refresh_token"),
            token_type=data.get("token_type", "Bearer"),
            scope=data.get("scope", ""),
            expiry=expiry,
        )


def make_state() -> str:
    """Generate a random state parameter for OAuth (CSRF protection)."""
    return secrets.token_urlsafe(32)


def verify_state(state: str) -> bool:
    """Verify the state is not empty (full validation would require session/cache)."""
    return bool(state and len(state) > 0)


def build_authorization_url(
    client_id: str,
    redirect_uri: str,
    tenant: str = "common",
    state: str = "",
    scope: str = "Mail.Read Mail.ReadWrite Mail.Send offline_access",
) -> str:
    """Build the Microsoft Entra ID authorization endpoint URL.

    Args:
        client_id: Azure AD app registration client ID
        redirect_uri: Callback URL registered in Azure AD
        tenant: Tenant ID or 'common' for multi-tenant
        state: CSRF protection token
        scope: Space-separated Microsoft Graph scopes

    Returns:
        Full authorization URL
    """
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
        "prompt": "select_account",  # Always show account picker
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{query}"


async def exchange_code(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    tenant: str = "common",
) -> OutlookTokens:
    """Exchange authorization code for access token.

    Args:
        code: Authorization code from callback
        client_id: Azure AD app registration client ID
        client_secret: Client secret (keep confidential)
        redirect_uri: Callback URL (must match authorization request)
        tenant: Tenant ID or 'common'

    Returns:
        OutlookTokens with access/refresh tokens

    Raises:
        OutlookOAuthError on failed exchange
    """
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "scope": "Mail.Read Mail.ReadWrite Mail.Send offline_access",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(token_url, data=payload)
            response.raise_for_status()
            data = response.json()
            return OutlookTokens.from_response(data)
    except httpx.HTTPStatusError as exc:
        try:
            error_data = exc.response.json()
            error_description = error_data.get("error_description", str(exc))
        except Exception:
            error_description = str(exc)
        logger.warning("outlook_oauth.exchange_failed", error=error_description)
        raise OutlookOAuthError(f"Token exchange failed: {error_description}") from exc
    except Exception as exc:
        logger.warning("outlook_oauth.exchange_error", error=str(exc))
        raise OutlookOAuthError(f"OAuth token exchange error: {exc}") from exc


async def refresh_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    tenant: str = "common",
) -> OutlookTokens:
    """Refresh an expired access token using the refresh token.

    Args:
        refresh_token: Refresh token from previous exchange
        client_id: Azure AD app registration client ID
        client_secret: Client secret
        tenant: Tenant ID or 'common'

    Returns:
        OutlookTokens with new access token

    Raises:
        OutlookOAuthError on failed refresh
    """
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": "Mail.Read Mail.ReadWrite Mail.Send offline_access",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(token_url, data=payload)
            response.raise_for_status()
            data = response.json()
            return OutlookTokens.from_response(data)
    except Exception as exc:
        logger.warning("outlook_oauth.refresh_failed", error=str(exc))
        raise OutlookOAuthError(f"Token refresh failed: {exc}") from exc
