"""Data-access layer for :class:`~app.models.google_credential.GoogleCredential`."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.google_credential import GoogleCredential


class GoogleCredentialRepository:
    """Encapsulates persistence of stored Google OAuth credentials."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_id(self, user_id: uuid.UUID) -> GoogleCredential | None:
        result = await self.session.execute(
            select(GoogleCredential).where(GoogleCredential.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        user_id: uuid.UUID,
        google_sub: str,
        google_email: str,
        access_token_enc: str,
        refresh_token_enc: str | None,
        token_expiry: datetime | None,
        scopes: str,
    ) -> GoogleCredential:
        """Create or update the one-to-one credential row for ``user_id``.

        A re-consent may omit the refresh token; in that case the previously
        stored one is preserved.
        """
        cred = await self.get_by_user_id(user_id)
        if cred is None:
            cred = GoogleCredential(user_id=user_id)
            self.session.add(cred)

        cred.google_sub = google_sub
        cred.google_email = google_email
        cred.access_token_enc = access_token_enc
        if refresh_token_enc:
            cred.refresh_token_enc = refresh_token_enc
        cred.token_expiry = token_expiry
        cred.scopes = scopes

        await self.session.commit()
        await self.session.refresh(cred)
        return cred

    async def update_access_token(
        self,
        cred: GoogleCredential,
        *,
        access_token_enc: str,
        token_expiry: datetime | None,
    ) -> GoogleCredential:
        """Persist a refreshed access token."""
        cred.access_token_enc = access_token_enc
        cred.token_expiry = token_expiry
        await self.session.commit()
        await self.session.refresh(cred)
        return cred
