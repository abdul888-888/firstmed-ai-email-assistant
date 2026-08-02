"""Gmail provider implementation using the Gmail REST API.

Wraps the existing Gmail REST logic with the ``BaseEmailProvider`` interface.
Handles transparent access-token refresh using the stored (encrypted) refresh
token. Reads messages (gmail.readonly) and creates reply *drafts*
(gmail.compose) — it never sends mail automatically; a human reviews and sends
every draft from Gmail.

All exceptions are translated to the standardised ``EmailProviderError`` and
``EmailProviderNotConnectedError`` types for consistency with other providers.
"""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import random
import re
from contextlib import asynccontextmanager
from email.message import EmailMessage
from typing import TYPE_CHECKING

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.email import NormalizedEmail
from app.services import google_oauth

from .base import BaseEmailProvider, EmailProviderError, EmailProviderNotConnectedError

if TYPE_CHECKING:
    from app.models.connected_account import ConnectedAccount
    from app.repositories.connected_account import ConnectedAccountRepository

logger = get_logger(__name__)

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"
_HTTP_TIMEOUT = 15.0
# Refresh proactively if the token expires within this window.
_EXPIRY_SKEW = dt.timedelta(seconds=60)

# --- retry/backoff on transient failures ------------------------------------
# Rate limiting (429) and server errors (5xx) are worth retrying with backoff;
# anything else (400/403/404/...) is a permanent failure for this request.
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 5
_BASE_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 30.0

# --- metadata-first fetch ----------------------------------------------------
# Labels that mark a message as noise (spam, our own sent/draft copies, or a
# tabbed category the account's own filters already sorted out). Checked from
# a CHEAP metadata-only fetch so the expensive full-body fetch is skipped
# entirely for these — this matters most for accounts without tabbed
# categories, where pull_gmail's negative-category search query is a no-op
# and every promotional email would otherwise cost a full MIME fetch AND an
# LLM triage call for nothing.
_NOISE_LABELS = frozenset(
    {
        "SPAM",
        "TRASH",
        "DRAFT",
        "SENT",
        "CATEGORY_PROMOTIONS",
        "CATEGORY_SOCIAL",
        "CATEGORY_FORUMS",
        "CATEGORY_UPDATES",
    }
)
_METADATA_HEADERS = ["Subject", "From", "To", "Date", "Message-ID"]

# Safety cap on history.list pagination (mirrors the pattern used for Notion).
_MAX_HISTORY_PAGES = 25


def _backoff_seconds(attempt: int, retry_after: str | None) -> float:
    """Exponential backoff with jitter; honors the server's Retry-After header
    when present (common on 429 responses) instead of guessing."""
    if retry_after:
        try:
            return min(_MAX_BACKOFF_SECONDS, max(0.0, float(retry_after)))
        except ValueError:
            pass
    base = min(_MAX_BACKOFF_SECONDS, _BASE_BACKOFF_SECONDS * (2**attempt))
    return base * (0.5 + random.random())


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t]*\n[ \t]*\n\s*")


def _decode_body(data: str | None) -> str:
    """Decode a Gmail base64url message body part (padding is often stripped)."""
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + padding).decode("utf-8", errors="replace")
    except ValueError:  # includes binascii.Error
        return ""


def _collect_bodies(part: dict) -> tuple[str, str]:
    """Walk a MIME part tree, returning the first (text/plain, text/html) bodies."""
    plain = html = ""
    mime = part.get("mimeType", "")
    data = part.get("body", {}).get("data")
    if mime == "text/plain":
        plain = _decode_body(data)
    elif mime == "text/html":
        html = _decode_body(data)
    for sub in part.get("parts") or []:
        sub_plain, sub_html = _collect_bodies(sub)
        plain = plain or sub_plain
        html = html or sub_html
    return plain, html


def _extract_body(payload: dict) -> str:
    """Extract a readable plain-text body from a full Gmail message payload.

    Prefers text/plain; falls back to a tag-stripped text/html part. Returns an
    empty string when no textual body is present (callers use the snippet).
    """
    plain, html = _collect_bodies(payload)
    if plain.strip():
        return plain.strip()
    if html.strip():
        stripped = _HTML_TAG_RE.sub(" ", html)
        return _WHITESPACE_RE.sub("\n\n", stripped).strip()
    return ""


class GmailProvider(BaseEmailProvider):
    """Gmail provider using the Gmail REST API.

    Translates all Gmail-specific errors to the standardised
    ``EmailProviderError`` / ``EmailProviderNotConnectedError`` hierarchy.
    """

    def __init__(
        self,
        account: ConnectedAccount,
        session: AsyncSession,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the Gmail provider.

        Args:
            account: The ConnectedAccount row with encrypted tokens.
            session: AsyncSession for token persistence via repository.
            http_client: Optional httpx.AsyncClient to reuse. If None, a new
                one is created for each request.
        """
        self.account = account
        self.session = session
        self._client = http_client
        # Lazy import to avoid circular dependency at module level
        from app.repositories.connected_account import ConnectedAccountRepository

        self.repo = ConnectedAccountRepository(session)

    @property
    def mailbox(self) -> str:
        """The mailbox to operate on ("me" or the configured shared inbox)."""
        return settings.gmail_shared_inbox or "me"

    @asynccontextmanager
    async def _http(self):
        if self._client is not None:
            yield self._client
        else:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                yield client

    # --- credential / token handling -----------------------------------------

    def _is_expired(self) -> bool:
        """Check if the stored access token is expired or will expire soon."""
        if self.account.token_expiry is None:
            return True
        expiry = self.account.token_expiry
        if expiry.tzinfo is None:  # SQLite may return naive datetimes
            expiry = expiry.replace(tzinfo=dt.UTC)
        return expiry <= dt.datetime.now(dt.UTC) + _EXPIRY_SKEW

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        """Return a valid access token, refreshing if needed."""
        if not self._is_expired():
            if self.account.access_token_enc is None:
                raise EmailProviderNotConnectedError("No access token stored")
            return crypto.decrypt(self.account.access_token_enc)

        if not self.account.refresh_token_enc:
            # Can't refresh — return whatever we have and let the API 401.
            if self.account.access_token_enc is None:
                raise EmailProviderNotConnectedError("No refresh token available")
            return crypto.decrypt(self.account.access_token_enc)

        refresh_token = crypto.decrypt(self.account.refresh_token_enc)
        try:
            tokens = await google_oauth.refresh_access_token(refresh_token, client=client)
        except Exception as exc:
            raise EmailProviderError(f"Failed to refresh token: {exc}") from exc

        await self.repo.update_access_token(
            self.account,
            access_token_enc=crypto.encrypt(tokens.access_token),
            token_expiry=tokens.expiry,
        )
        logger.info("gmail.token_refreshed", user_id=str(self.account.user_id))
        return tokens.access_token

    # --- public API (BaseEmailProvider contract) ----------------------------

    async def fetch_messages(
        self,
        history_id: str | None = None,
        *,
        max_results: int = 25,
        query: str | None = None,
    ) -> tuple[list[NormalizedEmail], str | None]:
        """Fetch messages incrementally or via full search.

        Returns (messages, new_cursor). Encapsulates the logic of
        ``list_new_messages`` from GmailService — uses incremental sync when
        a cursor is available, falls back to full list on first run or history
        expiry.
        """
        messages: list[NormalizedEmail] = []
        new_history_id: str | None = history_id

        if history_id:
            # Try incremental sync via history.list.
            history_data = await self._get_history(history_id)
            if not history_data.get("expired", False):
                message_ids = history_data.get("messages", [])
                for msg_dict in message_ids:
                    try:
                        msg = await self.get_message(msg_dict["id"])
                        messages.append(msg)
                    except EmailProviderError:
                        # Skip messages that cannot be fetched (rare, but possible).
                        logger.warning(
                            "gmail.message_fetch_failed",
                            message_id=msg_dict["id"],
                        )
                new_history_id = history_data.get("history_id", history_id)
                return messages, new_history_id

            # History expired — fall through to full list.
            logger.info(
                "gmail.history_expired",
                user_id=str(self.account.user_id),
                stale_history_id=history_id,
            )

        # Full list fallback (first run or history expired).
        message_ids = await self._list_messages(max_results=max_results, query=query)
        for msg_dict in message_ids:
            try:
                msg = await self.get_message(msg_dict["id"])
                messages.append(msg)
            except EmailProviderError:
                logger.warning(
                    "gmail.message_fetch_failed",
                    message_id=msg_dict["id"],
                )

        # Bootstrap or update the cursor for next time.
        profile = await self._get_profile()
        new_history_id = profile.get("history_id")

        return messages, new_history_id

    async def get_message(self, message_id: str) -> NormalizedEmail:
        """Fetch a Gmail message and return it as NormalizedEmail.

        Uses metadata-first fetch to detect noise messages and skip expensive
        full-body fetches when the message is already classified as spam/draft/etc.
        """
        # Step 1: metadata-first fetch (cheap, no MIME body).
        meta = await self._get(
            f"/users/{self.mailbox}/messages/{message_id}",
            params={"format": "metadata", "metadataHeaders": _METADATA_HEADERS},
        )

        label_ids = meta.get("labelIds", []) or []
        headers = {
            h["name"].lower(): h["value"] for h in meta.get("payload", {}).get("headers", [])
        }

        # Parse received_at from the Date header.
        date_str = headers.get("date", "")
        try:
            # email.utils.parsedate_to_datetime handles most RFC 2822 formats
            from email.utils import parsedate_to_datetime

            received_at = parsedate_to_datetime(date_str)
        except (TypeError, ValueError):
            # Fallback to UTC now if parsing fails.
            received_at = dt.datetime.now(dt.timezone.utc)

        # Step 2: check for noise labels. If noisy, skip expensive fetch.
        is_noise = bool(_NOISE_LABELS.intersection(label_ids))
        body = ""
        if is_noise:
            logger.info(
                "gmail.message_skipped_noise",
                message_id=message_id,
                label_ids=label_ids,
            )
        else:
            # Step 3: full fetch to extract body text.
            full = await self._get(
                f"/users/{self.mailbox}/messages/{message_id}",
                params={"format": "full"},
            )
            payload = full.get("payload", {})
            body = _extract_body(payload)

        # Build NormalizedEmail from the metadata and body.
        return NormalizedEmail(
            provider_type="gmail",
            external_message_id=meta.get("id", message_id),
            external_thread_id=meta.get("threadId", ""),
            sender=headers.get("from", ""),
            recipients=[headers.get("to", "")] if headers.get("to") else [],
            subject=headers.get("subject", ""),
            body_text=body,
            received_at=received_at,
            message_id_header=headers.get("message-id", ""),
            is_noise=is_noise,
            raw_headers={
                **headers,
                "snippet": meta.get("snippet", ""),
                "label_ids": ",".join(label_ids),
            },
        )

    async def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> str:
        """Create a reply draft in Gmail's Drafts folder.

        Returns the draft ID. Does not send — the draft is reviewed by a human
        and then sent via ``send_draft``.
        """
        message = EmailMessage()
        message["To"] = to
        message["Subject"] = subject
        if in_reply_to:
            # Threading headers so the reply nests under the original message.
            message["In-Reply-To"] = in_reply_to
            message["References"] = in_reply_to
        message.set_content(body)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        payload: dict[str, object] = {"message": {"raw": raw}}
        if thread_id:
            payload["message"]["threadId"] = thread_id  # type: ignore[index]

        data = await self._post(f"/users/{self.mailbox}/drafts", json=payload)
        draft_id = data.get("id", "")
        if not draft_id:
            raise EmailProviderError("No draft ID returned from create_draft")
        return draft_id

    async def send_draft(self, draft_id: str) -> str:
        """Send an existing draft.

        Uses the Gmail ``drafts.send`` endpoint (covered by the ``gmail.compose``
        scope). Only call after explicit human approval.

        Returns the sent message ID.
        """
        data = await self._post(
            f"/users/{self.mailbox}/drafts/send",
            json={"id": draft_id},
        )
        message_id = data.get("id", "")
        if not message_id:
            raise EmailProviderError("No message ID returned from send_draft")
        return message_id

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        thread_id: str | None = None,
    ) -> str:
        """Send a new email directly (no intermediate draft).

        Builds a raw MIME message and posts to ``/messages/send``.
        Returns the sent message ID.
        """
        message = EmailMessage()
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        payload: dict[str, object] = {"raw": raw}
        if thread_id:
            payload["threadId"] = thread_id

        data = await self._post(
            f"/users/{self.mailbox}/messages/send",
            json=payload,
        )
        message_id = data.get("id", "")
        if not message_id:
            raise EmailProviderError("No message ID returned from send_email")
        return message_id

    # --- private helpers for Gmail API access --------------------------------

    async def _list_messages(
        self, *, max_results: int = 25, query: str | None = None
    ) -> list[dict]:
        """Fetch a list of message metadata (IDs and thread IDs)."""
        params: dict[str, object] = {"maxResults": max_results}
        if query:
            params["q"] = query
        data = await self._get(f"/users/{self.mailbox}/messages", params=params)
        return [
            {"id": m["id"], "thread_id": m.get("threadId", "")}
            for m in data.get("messages", [])
        ]

    async def _get_profile(self) -> dict:
        """Fetch the mailbox's current historyId (sync cursor)."""
        data = await self._get(f"/users/{self.mailbox}/profile", params={})
        return {
            "email_address": data.get("emailAddress", ""),
            "history_id": str(data.get("historyId", "")),
        }

    async def _get_history(
        self, start_history_id: str, *, max_pages: int = _MAX_HISTORY_PAGES
    ) -> dict:
        """Messages added since start_history_id (Gmail history.list).

        Far cheaper than re-listing the whole inbox: only what changed comes
        back. Gmail expires history after roughly a week — a 404 for a too-old
        start_history_id is reported as ``expired=True``.
        """
        message_ids: list[dict] = []
        seen: set[str] = set()
        cursor: str | None = None
        new_history_id: str | None = None

        for _ in range(max_pages):
            params: dict[str, object] = {
                "startHistoryId": start_history_id,
                "historyTypes": "messageAdded",
            }
            if cursor:
                params["pageToken"] = cursor
            try:
                data = await self._get(
                    f"/users/{self.mailbox}/history",
                    params=params,
                )
            except EmailProviderError as exc:
                if exc.status_code == httpx.codes.NOT_FOUND:
                    return {"messages": [], "history_id": None, "expired": True}
                raise

            for record in data.get("history", []) or []:
                for added in record.get("messagesAdded", []) or []:
                    msg = added.get("message", {})
                    mid = msg.get("id")
                    if mid and mid not in seen:
                        seen.add(mid)
                        message_ids.append({"id": mid, "thread_id": msg.get("threadId", "")})

            new_history_id = str(data.get("historyId", "")) or new_history_id
            cursor = data.get("nextPageToken")
            if not cursor:
                break

        return {"messages": message_ids, "history_id": new_history_id, "expired": False}

    # --- low-level HTTP with one refresh-retry on 401 + backoff on 429/5xx --

    async def _get(self, path: str, *, params: dict) -> dict:
        """GET request with one 401 refresh-retry and exponential backoff."""
        async with self._http() as client:
            token = await self._access_token(client)
            resp = await self._send_with_retry(
                client, "GET", path, token, params=params
            )

            if resp.status_code == httpx.codes.UNAUTHORIZED and self.account.refresh_token_enc:
                # Token may have been revoked/expired early; force one refresh + retry.
                refresh_token = crypto.decrypt(self.account.refresh_token_enc)
                try:
                    tokens = await google_oauth.refresh_access_token(
                        refresh_token, client=client
                    )
                except Exception as exc:
                    raise EmailProviderError(f"Failed to refresh token: {exc}") from exc

                await self.repo.update_access_token(
                    self.account,
                    access_token_enc=crypto.encrypt(tokens.access_token),
                    token_expiry=tokens.expiry,
                )
                resp = await self._send_with_retry(
                    client, "GET", path, tokens.access_token, params=params
                )

        if resp.status_code != httpx.codes.OK:
            if resp.status_code == httpx.codes.UNAUTHORIZED:
                raise EmailProviderNotConnectedError(
                    f"Gmail API 401: not authenticated"
                )
            raise EmailProviderError(
                f"Gmail API {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
            )
        return resp.json()

    async def _post(self, path: str, *, json: dict) -> dict:
        """POST request with one 401 refresh-retry and exponential backoff."""
        async with self._http() as client:
            token = await self._access_token(client)
            resp = await self._send_with_retry(
                client, "POST", path, token, json=json
            )

            if resp.status_code == httpx.codes.UNAUTHORIZED and self.account.refresh_token_enc:
                refresh_token = crypto.decrypt(self.account.refresh_token_enc)
                try:
                    tokens = await google_oauth.refresh_access_token(
                        refresh_token, client=client
                    )
                except Exception as exc:
                    raise EmailProviderError(f"Failed to refresh token: {exc}") from exc

                await self.repo.update_access_token(
                    self.account,
                    access_token_enc=crypto.encrypt(tokens.access_token),
                    token_expiry=tokens.expiry,
                )
                resp = await self._send_with_retry(
                    client, "POST", path, tokens.access_token, json=json
                )

        if resp.status_code not in (httpx.codes.OK, httpx.codes.CREATED):
            if resp.status_code == httpx.codes.UNAUTHORIZED:
                raise EmailProviderNotConnectedError(
                    f"Gmail API 401: not authenticated"
                )
            raise EmailProviderError(
                f"Gmail API {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
            )
        return resp.json()

    @staticmethod
    async def _send_with_retry(
        client: httpx.AsyncClient,
        method: str,
        path: str,
        token: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> httpx.Response:
        """Send one request, retrying with exponential backoff on 429/5xx.

        Does NOT retry the 401 case — that is handled by the caller as a
        one-shot token-refresh-and-retry.
        """
        resp: httpx.Response | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = await client.request(
                    method,
                    f"{GMAIL_BASE}{path}",
                    params=params,
                    json=json,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError as exc:
                if attempt >= _MAX_RETRIES:
                    raise EmailProviderError(f"Gmail request failed: {exc}") from exc
                logger.warning(
                    "gmail.retrying_connection_error",
                    path=path,
                    attempt=attempt,
                    error=str(exc),
                )
                await asyncio.sleep(_backoff_seconds(attempt, None))
                continue

            if resp.status_code not in _RETRYABLE_STATUSES or attempt >= _MAX_RETRIES:
                return resp
            logger.warning(
                "gmail.retrying_status",
                path=path,
                status=resp.status_code,
                attempt=attempt,
            )
            await asyncio.sleep(
                _backoff_seconds(attempt, resp.headers.get("Retry-After"))
            )

        assert resp is not None  # loop always assigns or raises
        return resp
