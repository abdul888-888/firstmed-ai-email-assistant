"""Stored Google OAuth credentials for a staff user.

One row per user (one-to-one). Access/refresh tokens are stored *encrypted*
(Fernet) via :mod:`app.core.crypto`; this model only holds the ciphertext.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class GoogleCredential(Base, TimestampMixin):
    __tablename__ = "google_credentials"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    # Google's stable account identifier (OIDC ``sub``).
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    google_email: Mapped[str] = mapped_column(String(320), nullable=False)

    # Fernet ciphertext — never the raw tokens.
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Space-separated list of granted scopes.
    scopes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Gmail mailbox history cursor (users.history.list startHistoryId) for
    # incremental sync — lets pull_gmail fetch only messages that changed
    # since last time instead of re-listing the whole recent inbox. Null until
    # the first successful pull bootstraps it; Gmail expires history after
    # ~7 days, at which point a stale value is detected and re-bootstrapped.
    history_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<GoogleCredential user_id={self.user_id} email={self.google_email!r}>"
