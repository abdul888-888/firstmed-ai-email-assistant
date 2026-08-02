"""IMAP/SMTP provider for generic mail servers (Zimbra, custom servers, etc.).

Implements the BaseEmailProvider interface using:
- ``aioimaplib`` for async IMAP operations (fetch, search, flag)
- ``aiosmtplib`` for async SMTP operations (send)
- Standard library ``email`` module for MIME parsing and encoding

Supports both IMAP for retrieval and SMTP for sending, with credentials
stored encrypted in the ConnectedAccount row (imap_host, imap_port,
smtp_host, smtp_port, imap_username, imap_password_enc).

Lazy import guards ensure that if aioimaplib or aiosmtplib are missing,
a clear error message is raised at runtime (not at import time).
"""

from __future__ import annotations

import asyncio
import base64
from email import message_from_bytes, utils
from email.message import EmailMessage
from typing import TYPE_CHECKING

from app.core import crypto
from app.core.logging import get_logger

from .base import BaseEmailProvider, EmailProviderError, EmailProviderNotConnectedError

if TYPE_CHECKING:
    from app.models.connected_account import ConnectedAccount
    from app.schemas.email import NormalizedEmail

logger = get_logger(__name__)


def _check_aioimaplib():
    """Check if aioimaplib is available; raise with installation instructions if not."""
    try:
        import aioimaplib  # noqa: F401

        return aioimaplib
    except ImportError:
        raise RuntimeError(
            "aioimaplib is not installed. "
            "Install it with: pip install 'aioimaplib>=1.1.0,<2'"
        ) from None


def _check_aiosmtplib():
    """Check if aiosmtplib is available; raise with installation instructions if not."""
    try:
        import aiosmtplib  # noqa: F401

        return aiosmtplib
    except ImportError:
        raise RuntimeError(
            "aiosmtplib is not installed. "
            "Install it with: pip install 'aiosmtplib>=3.0.0,<4'"
        ) from None


class ImapSmtpProvider(BaseEmailProvider):
    """IMAP/SMTP provider for generic mail servers.

    Supports any mail server with IMAP and SMTP (Zimbra, Dovecot, etc.).
    Uses STARTTLS for encryption unless port 465 is configured (implicit TLS).

    Credentials are stored encrypted in the ConnectedAccount row.
    """

    def __init__(self, account: ConnectedAccount) -> None:
        """Initialize the IMAP/SMTP provider.

        Args:
            account: The ConnectedAccount row with IMAP/SMTP configuration.
                Must have imap_host, imap_port, smtp_host, smtp_port,
                imap_password_enc set.

        Raises:
            EmailProviderNotConnectedError: If required fields are missing.
            RuntimeError: If aioimaplib or aiosmtplib are not installed.
        """
        self.account = account
        # Validate that required fields are present.
        if not all(
            (
                account.imap_host,
                account.imap_port,
                account.smtp_host,
                account.smtp_port,
                account.imap_password_enc,
            )
        ):
            raise EmailProviderNotConnectedError(
                "IMAP/SMTP account missing required fields: "
                "imap_host, imap_port, smtp_host, smtp_port, imap_password_enc"
            )
        # Eager validation of dependencies at init time.
        _check_aioimaplib()
        _check_aiosmtplib()

    def _imap_username(self) -> str:
        """Get the IMAP login username."""
        return self.account.imap_username or self.account.provider_email

    def _imap_password(self) -> str:
        """Decrypt and return the IMAP password."""
        if not self.account.imap_password_enc:
            raise EmailProviderNotConnectedError("No IMAP password stored")
        return crypto.decrypt(self.account.imap_password_enc)

    async def fetch_messages(
        self,
        history_id: str | None = None,
        *,
        max_results: int = 25,
        query: str | None = None,
    ) -> tuple[list[NormalizedEmail], str | None]:
        """Fetch messages incrementally or via recent message search.

        ``history_id`` is treated as the last-seen UID. On subsequent calls,
        we search for UIDs greater than this value. On first call (history_id=None),
        we search for all recent messages up to ``max_results``.

        Returns (messages, new_cursor). Cursor is the string form of the max UID
        fetched, or None if no messages found.
        """
        aioimaplib = _check_aioimaplib()

        messages: list[NormalizedEmail] = []
        last_uid = None

        try:
            async with aioimaplib.IMAP4_SSL(
                self.account.imap_host, self.account.imap_port
            ) as imap:
                await imap.login(self._imap_username(), self._imap_password())
                await imap.select("INBOX")

                # Determine search criteria based on cursor.
                if history_id:
                    # Incremental: search for UIDs greater than last_uid.
                    try:
                        last_uid_int = int(history_id)
                    except ValueError:
                        # Invalid cursor; fall back to recent.
                        search_criterion = "RECENT"
                    else:
                        search_criterion = f"UID {last_uid_int + 1}:*"
                else:
                    # First run: search for recent messages.
                    search_criterion = "RECENT"

                # Execute search.
                _, uids_response = await imap.search(None, search_criterion)
                uid_list = uids_response[0].split() if uids_response[0] else []

                # Limit to max_results; UIDs are already sorted.
                uid_list = uid_list[-max_results:] if uid_list else []

                for uid in uid_list:
                    try:
                        msg = await self.get_message(uid.decode() if isinstance(uid, bytes) else uid)
                        messages.append(msg)
                        # Track the highest UID seen.
                        uid_int = int(uid) if isinstance(uid, bytes) else int(uid.decode())
                        if last_uid is None or uid_int > last_uid:
                            last_uid = uid_int
                    except EmailProviderError as exc:
                        logger.warning(
                            "imap_smtp.message_fetch_failed",
                            uid=uid,
                            error=str(exc),
                        )

        except EmailProviderNotConnectedError:
            raise
        except Exception as exc:
            raise EmailProviderError(f"IMAP fetch failed: {exc}") from exc

        # Return messages and the new cursor (max UID as string, or None).
        new_cursor = str(last_uid) if last_uid is not None else None
        return messages, new_cursor

    async def get_message(self, message_id: str) -> NormalizedEmail:
        """Fetch a single message by UID and return it as NormalizedEmail.

        ``message_id`` is the IMAP UID (as a string).
        """
        from app.schemas.email import NormalizedEmail
        import datetime as dt

        aioimaplib = _check_aioimaplib()

        try:
            async with aioimaplib.IMAP4_SSL(
                self.account.imap_host, self.account.imap_port
            ) as imap:
                await imap.login(self._imap_username(), self._imap_password())
                await imap.select("INBOX")

                # Fetch the full message RFC822.
                _, data = await imap.fetch(message_id, "RFC822")
                if not data or not data[0]:
                    raise EmailProviderError(
                        f"UID {message_id} not found",
                        status_code=404,
                    )

                # Parse the message.
                raw_msg = data[0][1]
                msg = message_from_bytes(raw_msg)

                # Extract headers.
                subject = msg.get("Subject", "") or ""
                sender = msg.get("From", "") or ""
                to = msg.get("To", "") or ""
                recipients = [to] if to else []
                message_id_header = msg.get("Message-ID", "") or ""

                # Extract Date → datetime.
                date_str = msg.get("Date", "")
                try:
                    received_at = utils.parsedate_to_datetime(date_str)
                except (TypeError, ValueError):
                    received_at = dt.datetime.now(dt.timezone.utc)

                # Extract body text (prefer text/plain).
                body_text = ""
                if msg.is_multipart():
                    for part in msg.iter_parts():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                try:
                                    body_text = payload.decode("utf-8", errors="replace")
                                except Exception:
                                    pass
                            break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        try:
                            body_text = payload.decode("utf-8", errors="replace")
                        except Exception:
                            pass

                # Build NormalizedEmail.
                return NormalizedEmail(
                    provider_type="imap_smtp",
                    external_message_id=message_id,
                    external_thread_id="",  # IMAP has no threading concept.
                    sender=sender,
                    recipients=recipients,
                    subject=subject,
                    body_text=body_text,
                    received_at=received_at,
                    message_id_header=message_id_header,
                    is_noise=False,  # IMAP providers don't auto-classify.
                    raw_headers={
                        "subject": subject,
                        "from": sender,
                        "to": to,
                        "date": date_str,
                        "message-id": message_id_header,
                    },
                )

        except EmailProviderNotConnectedError:
            raise
        except Exception as exc:
            raise EmailProviderError(f"IMAP message fetch failed: {exc}") from exc

    async def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> str:
        """Create a draft in the Drafts folder.

        Returns the UID of the appended message as the draft ID.
        """
        aioimaplib = _check_aioimaplib()

        try:
            # Build MIME message.
            message = EmailMessage()
            message["To"] = to
            message["Subject"] = subject
            if in_reply_to:
                message["In-Reply-To"] = in_reply_to
                message["References"] = in_reply_to
            message.set_content(body)

            async with aioimaplib.IMAP4_SSL(
                self.account.imap_host, self.account.imap_port
            ) as imap:
                await imap.login(self._imap_username(), self._imap_password())

                # Append to Drafts folder with Draft flag.
                _, response = await imap.append(
                    "Drafts",
                    message.as_bytes(),
                    ["\\Draft"],
                )

                # Parse UID from response (varies by server; typically "[UID 123]").
                if response and response[0]:
                    response_str = response[0].decode() if isinstance(response[0], bytes) else response[0]
                    # Try to extract UID from "[UID 123]" format.
                    if "UID" in response_str:
                        parts = response_str.split()
                        for i, part in enumerate(parts):
                            if part == "UID" and i + 1 < len(parts):
                                draft_id = parts[i + 1].rstrip("]")
                                return draft_id

                raise EmailProviderError("Could not determine draft UID from server response")

        except EmailProviderNotConnectedError:
            raise
        except Exception as exc:
            raise EmailProviderError(f"IMAP draft create failed: {exc}") from exc

    async def send_draft(self, draft_id: str) -> str:
        """Send a draft from the Drafts folder.

        Fetches the draft, sends it via SMTP, and marks the original as deleted.

        Returns the Message-ID of the sent message.
        """
        aioimaplib = _check_aioimaplib()

        try:
            # Step 1: Fetch the draft.
            draft_msg = await self.get_message(draft_id)

            # Step 2: Send via SMTP.
            sent_msg_id = await self.send_email(
                draft_msg.recipients[0] if draft_msg.recipients else "",
                draft_msg.subject,
                draft_msg.body_text,
            )

            # Step 3: Mark original as deleted in Drafts and expunge.
            async with aioimaplib.IMAP4_SSL(
                self.account.imap_host, self.account.imap_port
            ) as imap:
                await imap.login(self._imap_username(), self._imap_password())
                await imap.select("Drafts")
                await imap.store(draft_id, "+FLAGS", "(\\Deleted,)")
                await imap.expunge()

            return sent_msg_id

        except EmailProviderNotConnectedError:
            raise
        except Exception as exc:
            raise EmailProviderError(f"IMAP draft send failed: {exc}") from exc

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        thread_id: str | None = None,
    ) -> str:
        """Send a new email via SMTP.

        Returns the Message-ID header of the sent message.
        """
        aiosmtplib = _check_aiosmtplib()

        try:
            # Build MIME message.
            message = EmailMessage()
            message["To"] = to
            message["Subject"] = subject
            message.set_content(body)

            # Determine if we should use implicit TLS (port 465) or STARTTLS.
            use_ssl = self.account.smtp_port == 465

            async with aiosmtplib.SMTP(
                hostname=self.account.smtp_host,
                port=self.account.smtp_port,
                use_tls=use_ssl,
            ) as smtp:
                if not use_ssl:
                    # Use STARTTLS for port 587 or other non-465 ports.
                    await smtp.starttls()

                await smtp.login(
                    self.account.provider_email,
                    self._imap_password(),  # Assuming same password for SMTP.
                )
                await smtp.send_message(message)

            # Return the Message-ID (was set by EmailMessage).
            msg_id = message.get("Message-ID", "")
            if not msg_id:
                # Fallback: generate a simple ID if not present.
                import uuid
                import socket

                hostname = socket.gethostname()
                msg_id = f"<{uuid.uuid4()}@{hostname}>"

            return msg_id

        except EmailProviderNotConnectedError:
            raise
        except Exception as exc:
            raise EmailProviderError(f"SMTP send failed: {exc}") from exc
