"""Unified email schema shared across all provider implementations.

``NormalizedEmail`` is the single value object the provider layer returns to
the domain layer (WorkflowService, DraftService, AI pipeline).  Every concrete
provider — Gmail, Microsoft Graph, IMAP/SMTP — maps its native wire format to
this schema before handing results back to callers.  The domain layer never
imports provider-specific types.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NormalizedEmail(BaseModel):
    """A provider-agnostic representation of one inbound (or fetched) email.

    Immutable by design: downstream consumers (triage, draft generation,
    DraftReview persistence) must not mutate message data after it is
    normalised.  If a transformation is needed, build a new instance.

    Field notes
    -----------
    external_message_id
        The provider's opaque, stable identifier for this specific message.
        For Gmail this is the ``id`` field; for Graph it is the OData ``id``;
        for IMAP it is the string form of the UID in the selected mailbox.

    external_thread_id
        Provider's conversation/thread identifier.  Empty string when the
        provider has no threading concept (some IMAP servers).

    message_id_header
        The RFC 2822 ``Message-ID`` header value (e.g.
        ``<abc123@mail.example.com>``).  Used to set ``In-Reply-To`` /
        ``References`` headers on reply drafts so they nest correctly in the
        recipient's mail client.  Distinct from ``external_message_id``.

    is_noise
        True when the provider's own labels / flags already classify this
        message as non-actionable (spam, sent copy, draft, promotions, social,
        etc.).  The workflow engine skips triage and draft generation for noise
        messages, saving LLM quota.

    received_at
        Always UTC-aware.  The ``@field_validator`` coerces naive datetimes to
        UTC so callers don't have to remember timezone handling.

    raw_headers
        The original header map from the provider, lower-cased.  Kept for
        debugging and for any provider-specific header a consumer may need
        (e.g. ``x-original-to``, ``x-spam-status``).  Not used by the core
        pipeline.
    """

    model_config = ConfigDict(frozen=True)

    # --- provider identity ------------------------------------------------
    provider_type: Literal["gmail", "outlook", "imap_smtp"] = Field(
        description="Which email provider produced this message."
    )

    # --- provider-native identifiers -------------------------------------
    external_message_id: str = Field(
        description="Provider's opaque stable message identifier."
    )
    external_thread_id: str = Field(
        default="",
        description="Provider thread/conversation ID; empty if unsupported.",
    )

    # --- addressing -------------------------------------------------------
    sender: str = Field(
        description="RFC 5322 From address, e.g. 'Jane Doe <jane@example.com>'."
    )
    recipients: list[str] = Field(
        default_factory=list,
        description="To: addresses.  May be empty for received messages "
        "where To is not reliably parseable.",
    )

    # --- content ----------------------------------------------------------
    subject: str = Field(default="", description="Decoded subject line.")
    body_text: str = Field(
        default="",
        description=(
            "Plain-text body.  Providers should prefer text/plain parts; "
            "HTML is tag-stripped as a fallback.  May be empty — callers "
            "should fall back to a snippet stored in raw_headers['snippet'] "
            "when this field is empty."
        ),
    )

    # --- timestamps -------------------------------------------------------
    received_at: dt.datetime = Field(
        description="UTC-aware datetime the message was received by the server."
    )

    # --- threading --------------------------------------------------------
    message_id_header: str = Field(
        default="",
        description="RFC 2822 Message-ID header value for reply threading.",
    )

    # --- noise flag -------------------------------------------------------
    is_noise: bool = Field(
        default=False,
        description=(
            "True when the provider already classifies this message as "
            "non-actionable (spam, sent, draft, promotions, social, etc.)."
        ),
    )

    # --- debug / extensibility -------------------------------------------
    raw_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Lower-cased original headers from the provider.",
    )

    # --- identity / hashing -----------------------------------------------
    # Two NormalizedEmail objects are considered the *same message* when they
    # share (provider_type, external_message_id).  This lets the pull pipeline
    # deduplicate via a plain ``set()`` without building a separate ID set.
    #
    # Note: Pydantic's frozen=True generates __eq__ that compares ALL fields.
    # We override both __eq__ and __hash__ so they agree — Python requires that
    # objects which compare equal have the same hash.
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, NormalizedEmail):
            return NotImplemented
        return (
            self.provider_type == other.provider_type
            and self.external_message_id == other.external_message_id
        )

    def __hash__(self) -> int:  # type: ignore[override]
        return hash((self.provider_type, self.external_message_id))

    # --- validators -------------------------------------------------------

    @field_validator("received_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: object) -> dt.datetime:
        """Coerce naive datetimes to UTC; reject non-datetime inputs."""
        if isinstance(value, str):
            # Allow ISO 8601 strings — Pydantic handles the parse, but we
            # still need to enforce UTC awareness after parsing.
            parsed = dt.datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc)
        if isinstance(value, dt.datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=dt.timezone.utc)
            return value.astimezone(dt.timezone.utc)
        raise ValueError(f"received_at must be a datetime, got {type(value).__name__!r}")
