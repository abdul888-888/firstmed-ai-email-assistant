"""Data-access layer for :class:`~app.models.connected_account.ConnectedAccount`.

Mirrors the interface of :class:`~app.repositories.google_credential.GoogleCredentialRepository`
so the two can be swapped with minimal call-site changes during the Phase 1
migration.  All write operations commit and refresh the row before returning so
callers always receive a fully-populated, session-consistent object.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connected_account import ConnectedAccount
from app.models.user import User


class ConnectedAccountRepository:
    """Encapsulates persistence of multi-provider connected-account credentials."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── read ─────────────────────────────────────────────────────────────

    async def get_by_user_id(self, user_id: uuid.UUID) -> ConnectedAccount | None:
        """Return the connected account for ``user_id``, or ``None`` if the user
        has not linked any email provider yet."""
        result = await self.session.execute(
            select(ConnectedAccount).where(ConnectedAccount.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, account_id: uuid.UUID) -> ConnectedAccount | None:
        """Return the connected account by its primary key, or ``None``."""
        return await self.session.get(ConnectedAccount, account_id)

    async def list_connected_user_ids(self) -> list[uuid.UUID]:
        """Return the ``user_id`` of every active user with a connected account.

        The result set drives the Celery Beat fan-out: one pull task is enqueued
        per entry.  Only users whose ``User.is_active`` flag is ``True`` are
        included — deactivated accounts are silently skipped so their stale
        credentials don't accumulate pull failures.

        The join intentionally uses an INNER JOIN (the default for
        ``join()``): rows in ``connected_accounts`` that have no matching
        ``users`` row (orphaned credentials) are excluded.
        """
        result = await self.session.execute(
            select(ConnectedAccount.user_id)
            .join(User, User.id == ConnectedAccount.user_id)
            .where(User.is_active.is_(True))
        )
        return list(result.scalars().all())

    # ── write ────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        provider_type: str,
        provider_email: str,
        **kwargs: Any,
    ) -> ConnectedAccount:
        """Insert a new ``ConnectedAccount`` row and return the persisted object.

        ``provider_type`` must be one of ``'gmail'``, ``'outlook'``,
        ``'imap_smtp'`` (enforced at the Pydantic layer by the API, not here).

        Any additional column values can be passed as keyword arguments, e.g.::

            await repo.create(
                user_id=user.id,
                provider_type="gmail",
                provider_email="clinic@example.com",
                provider_sub="1234567890",
                access_token_enc=crypto.encrypt(token),
                refresh_token_enc=crypto.encrypt(refresh),
                token_expiry=expiry,
                scopes="openid email profile ...",
            )

        Raises ``sqlalchemy.exc.IntegrityError`` if a ``ConnectedAccount`` for
        this ``user_id`` already exists (unique constraint).  Callers that want
        upsert semantics should call :meth:`upsert` instead.
        """
        account = ConnectedAccount(
            user_id=user_id,
            provider_type=provider_type,
            provider_email=provider_email,
            **kwargs,
        )
        self.session.add(account)
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def upsert(
        self,
        *,
        user_id: uuid.UUID,
        provider_type: str,
        provider_email: str,
        **kwargs: Any,
    ) -> ConnectedAccount:
        """Create or replace the connected account for ``user_id``.

        If a row already exists it is updated in-place; otherwise a new one is
        created.  All supplied ``kwargs`` are applied to the row.  Fields not
        present in ``kwargs`` are left unchanged on an existing row (partial
        update semantics).

        This is the preferred entry point for OAuth callback handlers and the
        IMAP/SMTP connect endpoint, where a reconnect should silently overwrite
        stale credentials rather than fail with an integrity error.
        """
        account = await self.get_by_user_id(user_id)
        if account is None:
            return await self.create(
                user_id=user_id,
                provider_type=provider_type,
                provider_email=provider_email,
                **kwargs,
            )

        # Existing row — apply all supplied fields.
        account.provider_type = provider_type
        account.provider_email = provider_email
        for key, value in kwargs.items():
            setattr(account, key, value)

        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def update_history_id(
        self,
        account: ConnectedAccount,
        *,
        history_id: str,
    ) -> ConnectedAccount:
        """Persist the provider's incremental-sync cursor after a successful pull.

        Should be called immediately after ``provider.fetch_messages()`` returns
        a non-``None`` cursor so the next pull can resume from where this one
        left off rather than re-fetching the whole inbox.
        """
        account.history_id = history_id
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def update_access_token(
        self,
        account: ConnectedAccount,
        *,
        access_token_enc: str,
        token_expiry: datetime | None,
    ) -> ConnectedAccount:
        """Persist a refreshed OAuth access token.

        Called by the provider's internal token-refresh logic when the stored
        access token has expired and a new one has been obtained via the refresh
        token.  ``token_expiry`` is the UTC expiry of the new access token;
        pass ``None`` when the provider does not supply an expiry.
        """
        account.access_token_enc = access_token_enc
        account.token_expiry = token_expiry
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def delete(self, account: ConnectedAccount) -> None:
        """Remove a connected account (e.g. when a user disconnects their mailbox).

        The ``ON DELETE CASCADE`` foreign key ensures any child rows are also
        removed.  Note: this does NOT revoke the OAuth token at the provider —
        callers should do that separately when possible.
        """
        await self.session.delete(account)
        await self.session.commit()
