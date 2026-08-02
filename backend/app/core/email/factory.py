"""Factory function for instantiating email providers by account type.

Dispatches on ``ConnectedAccount.provider_type`` to the appropriate provider
class (GmailProvider, MSGraphProvider, ImapSmtpProvider).

The factory is the single point where the domain layer (WorkflowService,
DraftService, API routes) determines which provider to use. By centralizing
this dispatch, adding a new provider requires only:
1. A new provider class implementing BaseEmailProvider
2. An entry in _PROVIDER_MAP
3. No changes to call sites

Usage
-----
    from app.core.email import get_email_provider
    from app.models.connected_account import ConnectedAccount
    from app.repositories.connected_account import ConnectedAccountRepository
    from sqlalchemy.ext.asyncio import AsyncSession

    repo = ConnectedAccountRepository(session)
    account = await repo.get_by_user_id(user_id)
    if account is None:
        raise HTTPException(404, "No email account connected")

    provider = get_email_provider(account, session)
    messages, cursor = await provider.fetch_messages(history_id=account.history_id)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.connected_account import ConnectedAccount


def get_email_provider(
    account: ConnectedAccount,
    session: AsyncSession,
    *,
    http_client=None,
):
    """Get the appropriate email provider for a ConnectedAccount.

    Args:
        account: The ConnectedAccount row specifying provider type and credentials.
        session: AsyncSession for database operations (token persistence, etc.).
        http_client: Optional httpx.AsyncClient to reuse across requests.

    Returns:
        A BaseEmailProvider subclass instance (GmailProvider, MSGraphProvider,
        or ImapSmtpProvider) instantiated with the account and session.

    Raises:
        ValueError: If account.provider_type is not recognized.

    Examples:
        >>> provider = get_email_provider(account, session)
        >>> messages, cursor = await provider.fetch_messages(history_id="123")
    """
    from app.core.email.base import BaseEmailProvider
    from app.core.email.gmail import GmailProvider
    from app.core.email.imap_smtp import ImapSmtpProvider
    from app.core.email.outlook import MSGraphProvider

    _PROVIDER_MAP: dict[str, type[BaseEmailProvider]] = {
        "gmail": GmailProvider,
        "outlook": MSGraphProvider,
        "imap_smtp": ImapSmtpProvider,
    }

    provider_type = account.provider_type
    provider_class = _PROVIDER_MAP.get(provider_type)

    if provider_class is None:
        raise ValueError(
            f"Unknown provider type: {provider_type!r}. "
            f"Supported types: {', '.join(sorted(_PROVIDER_MAP.keys()))}"
        )

    # Instantiate the provider. ImapSmtpProvider doesn't need session or
    # http_client, so we handle its kwargs specially to avoid passing
    # unused parameters.
    if provider_type == "imap_smtp":
        return provider_class(account)
    else:
        return provider_class(account, session, http_client=http_client)
