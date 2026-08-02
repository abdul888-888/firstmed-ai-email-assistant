"""Email provider package.

Re-exports the public surface of the provider layer so consumers only need
a single import path:

    from app.core.email import BaseEmailProvider, get_email_provider
    from app.core.email import EmailProviderError, EmailProviderNotConnectedError
    from app.core.email import GmailProvider, MSGraphProvider, ImapSmtpProvider
"""

from __future__ import annotations

from app.core.email.base import (
    BaseEmailProvider,
    EmailProviderError,
    EmailProviderNotConnectedError,
)
from app.core.email.factory import get_email_provider
from app.core.email.gmail import GmailProvider
from app.core.email.imap_smtp import ImapSmtpProvider
from app.core.email.outlook import MSGraphProvider

__all__ = [
    "BaseEmailProvider",
    "EmailProviderError",
    "EmailProviderNotConnectedError",
    "get_email_provider",
    "GmailProvider",
    "MSGraphProvider",
    "ImapSmtpProvider",
]
