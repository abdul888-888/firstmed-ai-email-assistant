"""Abstract base class and shared exceptions for the email provider layer.

All concrete providers (Gmail, Microsoft Graph, IMAP/SMTP) inherit from
``BaseEmailProvider`` and translate their native exceptions into the two
standardised types defined here.  The domain layer (WorkflowService,
DraftService) imports only from this module — never from a concrete provider.

Exception hierarchy
-------------------
EmailProviderError
└── EmailProviderNotConnectedError   (no valid credentials for the account)

Usage
-----
    from app.core.email.base import BaseEmailProvider, EmailProviderError

    class MyProvider(BaseEmailProvider):
        async def fetch_messages(self, history_id=None, *, max_results=25, query=None):
            ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.email import NormalizedEmail


# ---------------------------------------------------------------------------
# Shared exceptions
# ---------------------------------------------------------------------------

class EmailProviderError(Exception):
    """Any provider-level API or network failure.

    ``status_code`` carries the HTTP (or IMAP/SMTP protocol) error code when
    available, so callers can distinguish rate-limit retries (429) from
    permanent auth failures (401/403) without parsing the message string.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"{type(self).__name__}({str(self)!r}, status_code={self.status_code!r})"
        )


class EmailProviderNotConnectedError(EmailProviderError):
    """The user has no valid credentials stored for this provider.

    Raised when the provider layer discovers that the required OAuth tokens,
    IMAP password, or other credentials are absent or irrevocably expired (i.e.
    a refresh is not possible).  Callers should surface this to the user as an
    "account not connected" state, not retry.
    """


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class BaseEmailProvider(ABC):
    """Strategy interface for email operations.

    Every concrete provider must implement all five abstract methods.  Methods
    are fully async — providers that wrap synchronous libraries (e.g. standard-
    library ``imaplib``) must wrap blocking calls with
    ``asyncio.get_event_loop().run_in_executor``.

    Error contract
    --------------
    Implementations MUST translate their native exceptions to either
    ``EmailProviderNotConnectedError`` (unrecoverable credential failure) or
    ``EmailProviderError`` (transient or API-level failure).  No provider-
    specific exception type (``GmailApiError``, ``SMTPException``, etc.) may
    leak through the public methods of this class.

    Cursor semantics
    ----------------
    ``history_id`` / cursor is an opaque string whose meaning is provider-
    specific:
    - Gmail: ``historyId`` integer (as string)
    - Microsoft Graph: ``$deltaLink`` URL
    - IMAP: highest seen UID (as string)

    Callers persist the returned cursor and pass it back on the next call to
    enable incremental sync.  Passing ``None`` always triggers a full fetch.
    """

    @abstractmethod
    async def fetch_messages(
        self,
        history_id: str | None = None,
        *,
        max_results: int = 25,
        query: str | None = None,
    ) -> tuple[list[NormalizedEmail], str | None]:
        """Return ``(messages, new_cursor)``.

        ``history_id`` is the provider's opaque incremental-sync cursor from
        the previous call.  Returns a fresh cursor alongside the messages so
        callers can persist it.  Returns ``None`` as the cursor only when the
        provider does not support incremental sync (unusual).

        ``query`` is a provider-native search expression (Gmail query syntax,
        Graph ``$filter``, or an IMAP SEARCH criterion).  It is applied only on
        the full-list fallback path; incremental sync paths ignore it.

        Implementations MUST NOT write the cursor to the database — that is
        the caller's responsibility (separation of concerns).
        """

    @abstractmethod
    async def get_message(self, message_id: str) -> NormalizedEmail:
        """Fetch and normalise a single message by its provider-native ID.

        Raises ``EmailProviderError`` if the message does not exist or cannot
        be retrieved.  Raises ``EmailProviderNotConnectedError`` if credentials
        are absent.
        """

    @abstractmethod
    async def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> str:
        """Create a draft reply in the provider's Drafts folder.

        ``thread_id`` and ``in_reply_to`` are used to attach the draft to the
        original conversation where supported.  ``in_reply_to`` is the RFC 2822
        ``Message-ID`` header value of the message being replied to.

        Returns the provider-native draft identifier (opaque string).
        """

    @abstractmethod
    async def send_draft(self, draft_id: str) -> str:
        """Send an existing draft identified by ``draft_id``.

        This is the outward-facing send path used by the human-in-the-loop
        ``approve → send`` workflow.  Only call after explicit human approval.

        Returns the provider-native message ID of the sent message.
        """

    @abstractmethod
    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        thread_id: str | None = None,
    ) -> str:
        """Send a new email directly without creating an intermediate draft.

        Used by providers (e.g. IMAP/SMTP) where the draft-then-send two-step
        is unnecessary or unsupported.

        Returns the provider-native message ID of the sent message.
        """
