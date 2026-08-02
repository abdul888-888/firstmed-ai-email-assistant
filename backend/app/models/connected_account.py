"""Connected email account credentials for all provider types.

One row per user (one-to-one via the unique constraint on ``user_id``).
This model supersedes ``GoogleCredential`` as the canonical credential store
and supports all three provider types defined in the Strategy Pattern refactor:

- ``'gmail'``      — Google OAuth tokens (access + refresh, Fernet-encrypted)
- ``'outlook'``    — Microsoft Graph OAuth tokens (access + refresh, Fernet-encrypted)
- ``'imap_smtp'``  — Generic IMAP/SMTP password (Fernet-encrypted) for Zimbra
                     and other custom mail servers

All secret material (tokens, passwords) is stored as Fernet ciphertext via
:mod:`app.core.crypto`.  The plaintext is NEVER written to this table.

``provider_type`` is stored as a plain ``String(20)`` rather than a SQLAlchemy
``Enum`` type — this avoids an ``ALTER TYPE`` on the database when a fourth
provider is added in the future; the allowed values are enforced at the Pydantic
layer (``NormalizedEmail.provider_type`` and the IMAP connect request schema).

Design notes
------------
- IMAP/SMTP fields (``imap_host`` … ``imap_password_enc``) are ``NULL`` for
  OAuth-based providers and must only be read when ``provider_type='imap_smtp'``.
- ``access_token_enc`` / ``refresh_token_enc`` are ``NULL`` for IMAP/SMTP
  accounts; ``imap_password_enc`` serves the same purpose there.
- ``history_id`` is provider-specific: Gmail ``historyId``, Graph
  ``$deltaLink``, or IMAP last-seen UID.  ``NULL`` until first successful pull.
- ``provider_sub`` is the provider's stable account identifier (Google OIDC
  ``sub``, Microsoft Entra OID).  Absent for IMAP/SMTP.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ConnectedAccount(Base, TimestampMixin):
    __tablename__ = "connected_accounts"

    __table_args__ = (
        # Enforce one connected account per user at the DB level — a second
        # INSERT for the same user_id is rejected before the app layer sees it.
        UniqueConstraint("user_id", name="uq_connected_accounts_user_id"),
        # Explicit named index for efficient get_by_user_id lookups.
        Index("ix_connected_accounts_user_id", "user_id"),
    )

    # ── primary key ──────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )

    # ── ownership ────────────────────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ── provider identity ────────────────────────────────────────────────
    # One of: 'gmail', 'outlook', 'imap_smtp'
    # Stored as VARCHAR(20); allowed values validated at the Pydantic layer.
    provider_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # The connected mailbox address (e.g. "clinic@example.com").
    provider_email: Mapped[str] = mapped_column(String(320), nullable=False)

    # Provider's stable account identifier (Google sub, Entra OID).
    # NULL for IMAP/SMTP accounts which have no such concept.
    provider_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── OAuth tokens (Gmail, Outlook) ────────────────────────────────────
    # Fernet ciphertext — never the raw token.
    # NULL for IMAP/SMTP accounts (use imap_password_enc instead).
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Space-separated list of granted OAuth scopes (empty for IMAP/SMTP).
    scopes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # ── incremental sync cursor ──────────────────────────────────────────
    # Provider-specific opaque value:
    #   Gmail    → historyId (integer stored as string)
    #   Outlook  → $deltaLink URL
    #   IMAP     → highest seen UID (integer stored as string)
    # NULL until the first successful pull bootstraps the cursor.
    history_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── IMAP/SMTP fields (imap_smtp only) ────────────────────────────────
    imap_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # IMAP login username when it differs from ``provider_email``
    # (common on Zimbra where the login is "user" but the address is
    # "user@domain.com").  Falls back to ``provider_email`` when NULL.
    imap_username: Mapped[str | None] = mapped_column(String(320), nullable=True)

    # Fernet ciphertext of the IMAP/SMTP password.
    # NULL for OAuth-based providers.
    imap_password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<ConnectedAccount user_id={self.user_id} "
            f"provider={self.provider_type!r} email={self.provider_email!r}>"
        )
