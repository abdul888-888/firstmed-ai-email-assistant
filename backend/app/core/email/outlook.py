"""Microsoft Graph provider for Outlook integration.

Implements email operations via the Microsoft Graph API:
https://graph.microsoft.com/v1.0/me/messages
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from app.core.crypto import decrypt
from app.core.logging import get_logger

from .base import BaseEmailProvider, EmailProviderError, EmailProviderNotConnectedError

if TYPE_CHECKING:
    from app.models.connected_account import ConnectedAccount
    from app.schemas.email import NormalizedEmail

logger = get_logger(__name__)

_GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
_GRAPH_SCOPES = "Mail.Read Mail.ReadWrite Mail.Send offline_access"


class MSGraphProvider(BaseEmailProvider):
    """Microsoft Graph provider for Outlook/Microsoft 365.

    Implements the BaseEmailProvider interface using OAuth 2.0 access tokens
    and the Microsoft Graph API for message access, draft creation, and sending.
    """

    def __init__(
        self,
        account: ConnectedAccount,
        session=None,
        *,
        http_client=None,
    ) -> None:
        """Initialize the Outlook provider.

        Args:
            account: ConnectedAccount with encrypted OAuth tokens (provider_type="outlook").
            session: Unused (for interface compatibility with GmailProvider).
            http_client: Optional HTTP client (defaults to httpx.AsyncClient).
        """
        self.account = account
        self.session = session
        self._http_client = http_client

    async def _get_access_token(self) -> str:
        """Get the current access token, refreshing if needed.

        Returns:
            Valid access token string.

        Raises:
            EmailProviderNotConnectedError if token missing or refresh fails.
        """
        if not self.account.access_token_enc:
            raise EmailProviderNotConnectedError(
                "Outlook account not connected (missing access token)"
            )

        try:
            token = decrypt(self.account.access_token_enc)
        except Exception as exc:
            logger.warning(
                "outlook.decrypt_token_failed",
                account_id=str(self.account.id),
                error=str(exc),
            )
            raise EmailProviderNotConnectedError(
                "Failed to decrypt Outlook access token"
            ) from exc

        # Check if token is expired (with 5-min buffer)
        if self.account.token_expiry:
            from datetime import timedelta

            now = datetime.utcnow()
            if now + timedelta(minutes=5) >= self.account.token_expiry:
                # Token expired; attempt refresh if we have a refresh token
                if self.account.refresh_token_enc:
                    return await self._refresh_token()

        return token

    async def _refresh_token(self) -> str:
        """Refresh the Outlook access token using the refresh token.

        Returns:
            New access token.

        Raises:
            EmailProviderNotConnectedError if refresh fails.
        """
        if not self.account.refresh_token_enc:
            raise EmailProviderNotConnectedError(
                "Outlook refresh token missing; re-connect account"
            )

        try:
            refresh_token_str = decrypt(self.account.refresh_token_enc)
        except Exception as exc:
            raise EmailProviderNotConnectedError(
                "Failed to decrypt Outlook refresh token"
            ) from exc

        # Import here to avoid hard dependency
        try:
            from app.services import outlook_oauth
        except ImportError:
            raise EmailProviderError(
                "outlook_oauth service not available", status_code=503
            )

        try:
            from app.core.config import settings

            new_tokens = await outlook_oauth.refresh_access_token(
                refresh_token=refresh_token_str,
                client_id=settings.outlook_client_id,
                client_secret=settings.outlook_client_secret.get_secret_value(),
                tenant=settings.outlook_tenant_id,
            )

            # Update the account record with new tokens (this is optional in this task;
            # full token persistence would require a session.commit() here)
            from app.core.crypto import encrypt

            self.account.access_token_enc = encrypt(new_tokens.access_token)
            self.account.token_expiry = new_tokens.expiry
            if new_tokens.refresh_token:
                self.account.refresh_token_enc = encrypt(new_tokens.refresh_token)
            # Note: In a real implementation, we'd persist these changes to the DB

            return new_tokens.access_token
        except Exception as exc:
            logger.warning(
                "outlook.token_refresh_failed",
                account_id=str(self.account.id),
                error=str(exc),
            )
            raise EmailProviderNotConnectedError(
                "Outlook token refresh failed; re-connect account"
            ) from exc

    async def _get(
        self, endpoint: str, *, headers: dict | None = None, **kwargs
    ) -> dict:
        """Make an authenticated GET request to Microsoft Graph.

        Args:
            endpoint: API endpoint path (e.g., "/me/messages")
            headers: Optional additional headers.
            **kwargs: Additional arguments to pass to httpx (params, etc.)

        Returns:
            Parsed JSON response.

        Raises:
            EmailProviderError on HTTP errors.
        """
        token = await self._get_access_token()
        h = {"Authorization": f"Bearer {token}"}
        if headers:
            h.update(headers)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{_GRAPH_API_BASE}{endpoint}",
                    headers=h,
                    **kwargs,
                )
                if response.status_code == 401:
                    # Token expired; refresh and retry once
                    new_token = await self._refresh_token()
                    h["Authorization"] = f"Bearer {new_token}"
                    response = await client.get(
                        f"{_GRAPH_API_BASE}{endpoint}",
                        headers=h,
                        **kwargs,
                    )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise EmailProviderNotConnectedError(
                    "Outlook authentication failed; account may be disconnected"
                ) from exc
            raise EmailProviderError(
                f"Outlook API error: {exc.response.status_code}",
                status_code=exc.response.status_code,
            ) from exc

    async def _post(
        self, endpoint: str, *, json=None, headers: dict | None = None, **kwargs
    ) -> dict:
        """Make an authenticated POST request to Microsoft Graph.

        Args:
            endpoint: API endpoint path.
            json: JSON request body.
            headers: Optional additional headers.
            **kwargs: Additional arguments to pass to httpx.

        Returns:
            Parsed JSON response.

        Raises:
            EmailProviderError on HTTP errors.
        """
        token = await self._get_access_token()
        h = {"Authorization": f"Bearer {token}"}
        if headers:
            h.update(headers)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{_GRAPH_API_BASE}{endpoint}",
                    headers=h,
                    json=json,
                    **kwargs,
                )
                if response.status_code == 401:
                    new_token = await self._refresh_token()
                    h["Authorization"] = f"Bearer {new_token}"
                    response = await client.post(
                        f"{_GRAPH_API_BASE}{endpoint}",
                        headers=h,
                        json=json,
                        **kwargs,
                    )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise EmailProviderNotConnectedError(
                    "Outlook authentication failed"
                ) from exc
            raise EmailProviderError(
                f"Outlook API error: {exc.response.status_code}",
                status_code=exc.response.status_code,
            ) from exc

    def _normalize_message(self, msg: dict) -> NormalizedEmail:
        """Convert a Microsoft Graph message to NormalizedEmail.

        Args:
            msg: Message dict from Microsoft Graph API.

        Returns:
            NormalizedEmail instance.
        """
        from app.schemas.email import NormalizedEmail

        # Parse sender email
        sender_obj = msg.get("from", {})
        sender_email = ""
        if isinstance(sender_obj, dict):
            sender_obj = sender_obj.get("emailAddress", {})
            if isinstance(sender_obj, dict):
                sender_email = sender_obj.get("address", "")

        # Parse recipients (to)
        recipients = []
        for addr_obj in msg.get("toRecipients", []):
            if isinstance(addr_obj, dict):
                addr = addr_obj.get("emailAddress", {})
                if isinstance(addr, dict):
                    recipients.append(addr.get("address", ""))

        # Body text (prefer plain text if available)
        body_text = ""
        body_preview = msg.get("bodyPreview", "")
        if msg.get("body"):
            body_obj = msg.get("body", {})
            if isinstance(body_obj, dict):
                body_text = body_obj.get("content", "")
        if not body_text:
            body_text = body_preview

        # Received date
        received_at_str = msg.get("receivedDateTime", "")
        received_at = None
        if received_at_str:
            try:
                # ISO 8601 format: "2024-01-15T10:30:00Z"
                received_at = datetime.fromisoformat(received_at_str.replace("Z", "+00:00"))
            except Exception:
                pass

        return NormalizedEmail(
            provider_type="outlook",
            external_message_id=msg.get("id", ""),
            external_thread_id=msg.get("conversationId", ""),
            sender=sender_email,
            recipients=recipients,
            subject=msg.get("subject", ""),
            body_text=body_text,
            received_at=received_at or datetime.utcnow(),
            message_id_header=msg.get("id", ""),
            is_noise=False,  # Graph API doesn't categorize as noise; caller can filter
            raw_headers=msg.get("internetMessageHeaders", []),
        )

    async def fetch_messages(
        self,
        history_id: str | None = None,
        *,
        max_results: int = 25,
        query: str | None = None,
    ) -> tuple[list[NormalizedEmail], str | None]:
        """Fetch messages from the mailbox.

        Supports incremental sync via $deltaToken (stored in history_id).

        Args:
            history_id: Delta token from previous fetch (optional).
            max_results: Maximum messages to return (default 25).
            query: Optional filter query.

        Returns:
            Tuple of (list of NormalizedEmail, new delta token).
        """
        # Build Graph query
        params = {
            "$top": min(max_results, 50),  # Graph API max is 50
            "$orderby": "receivedDateTime desc",
        }

        if history_id:
            # Use delta link from previous fetch
            params["$deltaToken"] = history_id

        if query:
            params["$filter"] = query

        try:
            result = await self._get("/me/messages", params=params)
        except EmailProviderNotConnectedError:
            raise
        except Exception as exc:
            raise EmailProviderError(f"Failed to fetch Outlook messages: {exc}") from exc

        messages = []
        for msg_data in result.get("value", []):
            try:
                messages.append(self._normalize_message(msg_data))
            except Exception as exc:
                logger.warning(
                    "outlook.normalize_failed",
                    message_id=msg_data.get("id"),
                    error=str(exc),
                )
                continue

        # Return next delta token for incremental sync
        next_token = result.get("@odata.deltaLink", None)
        # If no deltaLink, return the last message ID as cursor (fallback)
        if not next_token and messages:
            next_token = messages[-1].external_message_id

        return messages, next_token

    async def get_message(self, message_id: str) -> NormalizedEmail:
        """Fetch a single message by ID.

        Args:
            message_id: Microsoft Graph message ID.

        Returns:
            NormalizedEmail instance.

        Raises:
            EmailProviderError if not found or on API error.
        """
        try:
            msg = await self._get(f"/me/messages/{message_id}")
            return self._normalize_message(msg)
        except EmailProviderNotConnectedError:
            raise
        except Exception as exc:
            raise EmailProviderError(
                f"Failed to fetch Outlook message {message_id}: {exc}"
            ) from exc

    async def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> str:
        """Create a draft message.

        Args:
            to: Recipient email address.
            subject: Email subject.
            body: Email body (plain text).
            thread_id: Conversation ID for threading (optional).
            in_reply_to: Message ID to reply to (optional).

        Returns:
            Draft message ID.
        """
        draft_data = {
            "subject": subject,
            "body": {"contentType": "text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        }

        if in_reply_to:
            # Create a reply draft
            try:
                result = await self._post(
                    f"/me/messages/{in_reply_to}/createReply",
                    json={},
                )
                draft_id = result.get("id")
                # Update the draft with our content
                await self._post(
                    f"/me/messages/{draft_id}",
                    json={"subject": subject, "body": draft_data["body"]},
                )
                return draft_id
            except Exception as exc:
                raise EmailProviderError(
                    f"Failed to create Outlook reply draft: {exc}"
                ) from exc
        else:
            # Create a new message draft
            try:
                result = await self._post("/me/messages", json=draft_data)
                return result.get("id", "")
            except Exception as exc:
                raise EmailProviderError(
                    f"Failed to create Outlook draft: {exc}"
                ) from exc

    async def send_draft(self, draft_id: str) -> str:
        """Send an existing draft.

        Args:
            draft_id: Draft message ID.

        Returns:
            Sent message ID.
        """
        try:
            await self._post(f"/me/messages/{draft_id}/send", json={})
            # The sent message ID is the same as the draft ID
            return draft_id
        except Exception as exc:
            raise EmailProviderError(f"Failed to send Outlook draft: {exc}") from exc

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        thread_id: str | None = None,
    ) -> str:
        """Send a new email directly (not as a draft).

        Args:
            to: Recipient email address.
            subject: Email subject.
            body: Email body (plain text).
            thread_id: Unused (for interface compatibility).

        Returns:
            Sent message ID (if available from response).
        """
        message_data = {
            "subject": subject,
            "body": {"contentType": "text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
            "saveToSentItems": "true",
        }

        try:
            await self._post("/me/sendMail", json={"message": message_data})
            # Graph API /sendMail doesn't return a message ID; generate a placeholder
            import uuid

            return str(uuid.uuid4())
        except Exception as exc:
            raise EmailProviderError(f"Failed to send Outlook email: {exc}") from exc
