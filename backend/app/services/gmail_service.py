"""Gmail access for the shared clinical inbox (Phase 2).

Wraps the Gmail REST API with ``httpx`` (async). Handles transparent access-token
refresh using the stored (encrypted) refresh token. Reads messages (gmail.readonly)
and creates reply *drafts* (gmail.compose) — it never sends mail automatically;
a human reviews and sends every draft from Gmail.
"""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import random
import re
from contextlib import asynccontextmanager
from email.message import EmailMessage

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.config import settings
from app.core.logging import get_logger
from app.models.google_credential import GoogleCredential
from app.models.user import User
from app.repositories.google_credential import GoogleCredentialRepository
from app.services import google_oauth

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


class GmailError(Exception):
    """Base class for Gmail service errors."""


class GmailNotConnectedError(GmailError):
    """The user has not linked a Google account with Gmail scope."""


class GmailApiError(GmailError):
    """The Gmail API returned an error response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GmailService:
    def __init__(self, session: AsyncSession, *, client: httpx.AsyncClient | None = None) -> None:
        self.session = session
        self.repo = GoogleCredentialRepository(session)
        self._client = client

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

    # --- credential / token handling -------------------------------------

    async def _require_credential(self, user: User) -> GoogleCredential:
        cred = await self.repo.get_by_user_id(user.id)
        if cred is None:
            raise GmailNotConnectedError("Google account is not connected")
        return cred

    def _is_expired(self, cred: GoogleCredential) -> bool:
        if cred.token_expiry is None:
            return True
        expiry = cred.token_expiry
        if expiry.tzinfo is None:  # SQLite may return naive datetimes
            expiry = expiry.replace(tzinfo=dt.UTC)
        return expiry <= dt.datetime.now(dt.UTC) + _EXPIRY_SKEW

    async def _access_token(self, cred: GoogleCredential, client: httpx.AsyncClient) -> str:
        """Return a valid access token, refreshing if needed."""
        if not self._is_expired(cred):
            return crypto.decrypt(cred.access_token_enc)

        if not cred.refresh_token_enc:
            # Can't refresh — return whatever we have and let the API 401.
            return crypto.decrypt(cred.access_token_enc)

        refresh_token = crypto.decrypt(cred.refresh_token_enc)
        tokens = await google_oauth.refresh_access_token(refresh_token, client=client)
        await self.repo.update_access_token(
            cred,
            access_token_enc=crypto.encrypt(tokens.access_token),
            token_expiry=tokens.expiry,
        )
        logger.info("gmail.token_refreshed", user_id=str(cred.user_id))
        return tokens.access_token

    # --- public API -------------------------------------------------------

    async def get_connection(self, user: User):
        from app.schemas.gmail import GmailConnection

        cred = await self.repo.get_by_user_id(user.id)
        if cred is None:
            return GmailConnection(connected=False, mailbox=self.mailbox)
        return GmailConnection(
            connected=True,
            email=cred.google_email,
            scopes=cred.scopes.split() if cred.scopes else [],
            mailbox=self.mailbox,
        )

    async def list_messages(
        self, user: User, *, max_results: int = 25, query: str | None = None
    ) -> dict:
        cred = await self._require_credential(user)
        params: dict[str, object] = {"maxResults": max_results}
        if query:
            params["q"] = query
        data = await self._get(cred, f"/users/{self.mailbox}/messages", params=params)
        messages = [
            {"id": m["id"], "thread_id": m.get("threadId", "")} for m in data.get("messages", [])
        ]
        return {
            "messages": messages,
            "result_size_estimate": int(data.get("resultSizeEstimate", 0)),
            "mailbox": self.mailbox,
        }

    async def get_message(self, user: User, message_id: str) -> dict:
        """Fetch a Gmail message, metadata first.

        Step 1 is always a cheap ``format=metadata`` request (headers + labels
        + snippet — no MIME body, far less quota than ``format=full``). If the
        account's own labels already mark this message as noise (spam, our own
        sent/draft copy, or a tabbed category — see ``_NOISE_LABELS``), we
        return immediately with ``is_noise=True`` and an empty body, skipping
        the expensive full-body fetch (and, upstream, the LLM triage call)
        entirely. Only non-noise messages get the follow-up ``format=full``
        fetch needed to extract real body text for triage/drafting.
        """
        cred = await self._require_credential(user)
        meta = await self._get(
            cred,
            f"/users/{self.mailbox}/messages/{message_id}",
            params={"format": "metadata", "metadataHeaders": _METADATA_HEADERS},
        )
        label_ids = meta.get("labelIds", []) or []
        headers = {h["name"].lower(): h["value"] for h in meta.get("payload", {}).get("headers", [])}
        base = {
            "id": meta.get("id", message_id),
            "thread_id": meta.get("threadId", ""),
            "snippet": meta.get("snippet", ""),
            "subject": headers.get("subject", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "date": headers.get("date", ""),
            # RFC822 Message-ID header — used to thread reply drafts correctly.
            "message_id_header": headers.get("message-id", ""),
            "label_ids": label_ids,
        }
        if _NOISE_LABELS.intersection(label_ids):
            logger.info("gmail.message_skipped_noise", message_id=message_id, label_ids=label_ids)
            return {**base, "body": "", "is_noise": True}

        # ``full`` returns the complete MIME payload so we can extract the body,
        # not just the truncated snippet.
        full = await self._get(
            cred, f"/users/{self.mailbox}/messages/{message_id}", params={"format": "full"}
        )
        payload = full.get("payload", {})
        return {**base, "body": _extract_body(payload), "is_noise": False}

    async def get_profile(self, user: User) -> dict:
        """The mailbox's current ``historyId`` — the sync cursor for
        incremental fetching (see ``list_new_messages``)."""
        cred = await self._require_credential(user)
        data = await self._get(cred, f"/users/{self.mailbox}/profile", params={})
        return {
            "email_address": data.get("emailAddress", ""),
            "history_id": str(data.get("historyId", "")),
        }

    async def get_history(
        self, user: User, start_history_id: str, *, max_pages: int = _MAX_HISTORY_PAGES
    ) -> dict:
        """Messages added since ``start_history_id`` (Gmail ``users.history.list``).

        Far cheaper than re-listing the whole recent inbox on every pull: only
        what actually changed comes back. Gmail expires history after roughly
        a week — a ``404`` for a too-old ``start_history_id`` is reported as
        ``expired=True`` rather than raised, so the caller can fall back to a
        full list and re-bootstrap the cursor.
        """
        cred = await self._require_credential(user)
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
                data = await self._get(cred, f"/users/{self.mailbox}/history", params=params)
            except GmailApiError as exc:
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

    async def list_new_messages(
        self, user: User, *, max_results: int = 25, query: str | None = None
    ) -> dict:
        """Incrementally-aware replacement for ``list_messages``.

        If the credential has a stored ``history_id``, fetches only messages
        added since then (cheap) and advances the cursor. On the very first
        pull (no cursor yet) or once Gmail's history has expired, falls back
        to the bounded ``list_messages`` search and bootstraps a fresh cursor
        via ``get_profile`` so subsequent pulls can go incremental. The
        history path deliberately ignores ``max_results`` — it returns
        everything new since last time (typically small for a periodic pull),
        so nothing found is ever silently dropped by a batch-size cap; only
        the fallback full-list path is bounded by ``max_results``.
        """
        cred = await self._require_credential(user)

        if cred.history_id:
            history = await self.get_history(user, cred.history_id)
            if not history["expired"]:
                if history["history_id"]:
                    await self.repo.update_history_id(cred, history_id=history["history_id"])
                return {
                    "messages": history["messages"],
                    "mailbox": self.mailbox,
                    "synced_via": "history",
                }
            logger.info(
                "gmail.history_expired", user_id=str(user.id), stale_history_id=cred.history_id
            )

        listing = await self.list_messages(user, max_results=max_results, query=query)
        profile = await self.get_profile(user)
        if profile["history_id"]:
            await self.repo.update_history_id(cred, history_id=profile["history_id"])
        return {
            "messages": listing["messages"],
            "mailbox": self.mailbox,
            "synced_via": "full_list",
        }

    async def list_drafts(self, user: User, *, max_results: int = 25) -> dict:
        cred = await self._require_credential(user)
        data = await self._get(
            cred, f"/users/{self.mailbox}/drafts", params={"maxResults": max_results}
        )
        drafts = [
            {
                "id": d["id"],
                "message_id": d.get("message", {}).get("id", ""),
                "thread_id": d.get("message", {}).get("threadId", ""),
            }
            for d in data.get("drafts", [])
        ]
        return {
            "drafts": drafts,
            "result_size_estimate": int(data.get("resultSizeEstimate", 0)),
            "mailbox": self.mailbox,
        }

    async def create_draft(
        self,
        user: User,
        *,
        to: str,
        subject: str,
        body: str,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> dict:
        """Create a reply draft in the mailbox's Drafts folder (never sends).

        ``thread_id``/``in_reply_to`` keep the draft attached to the original
        conversation so staff see it as a reply, not a new thread.
        """
        cred = await self._require_credential(user)

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

        data = await self._post(cred, f"/users/{self.mailbox}/drafts", json=payload)
        return {
            "draft_id": data.get("id", ""),
            "message_id": data.get("message", {}).get("id", ""),
            "thread_id": data.get("message", {}).get("threadId", thread_id or ""),
        }

    async def send_draft(self, user: User, draft_id: str) -> dict:
        """Send an existing draft. Outward-facing — actually delivers the email.

        Uses the Gmail ``drafts.send`` endpoint (covered by the ``gmail.compose``
        scope). Only call after explicit human approval.
        """
        cred = await self._require_credential(user)
        data = await self._post(
            cred, f"/users/{self.mailbox}/drafts/send", json={"id": draft_id}
        )
        return {
            "message_id": data.get("id", ""),
            "thread_id": data.get("threadId", ""),
            "label_ids": data.get("labelIds", []),
        }

    # --- low-level GET with one refresh-retry on 401 + backoff on 429/5xx --

    async def _get(self, cred: GoogleCredential, path: str, *, params: dict) -> dict:
        async with self._http() as client:
            token = await self._access_token(cred, client)
            resp = await self._send_with_retry(client, "GET", path, token, params=params)

            if resp.status_code == httpx.codes.UNAUTHORIZED and cred.refresh_token_enc:
                # Token may have been revoked/expired early; force one refresh + retry.
                refresh_token = crypto.decrypt(cred.refresh_token_enc)
                tokens = await google_oauth.refresh_access_token(refresh_token, client=client)
                await self.repo.update_access_token(
                    cred,
                    access_token_enc=crypto.encrypt(tokens.access_token),
                    token_expiry=tokens.expiry,
                )
                resp = await self._send_with_retry(
                    client, "GET", path, tokens.access_token, params=params
                )

        if resp.status_code != httpx.codes.OK:
            raise GmailApiError(f"Gmail API {resp.status_code}: {resp.text}", status_code=resp.status_code)
        return resp.json()

    # --- low-level POST with one refresh-retry on 401 + backoff on 429/5xx -

    async def _post(self, cred: GoogleCredential, path: str, *, json: dict) -> dict:
        async with self._http() as client:
            token = await self._access_token(cred, client)
            resp = await self._send_with_retry(client, "POST", path, token, json=json)

            if resp.status_code == httpx.codes.UNAUTHORIZED and cred.refresh_token_enc:
                refresh_token = crypto.decrypt(cred.refresh_token_enc)
                tokens = await google_oauth.refresh_access_token(refresh_token, client=client)
                await self.repo.update_access_token(
                    cred,
                    access_token_enc=crypto.encrypt(tokens.access_token),
                    token_expiry=tokens.expiry,
                )
                resp = await self._send_with_retry(
                    client, "POST", path, tokens.access_token, json=json
                )

        if resp.status_code not in (httpx.codes.OK, httpx.codes.CREATED):
            raise GmailApiError(f"Gmail API {resp.status_code}: {resp.text}", status_code=resp.status_code)
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
        """Send one request, retrying with exponential backoff on 429/5xx and
        on transient connection errors. Does NOT retry the 401 case — that is
        handled by the caller as a one-shot token-refresh-and-retry, wrapping
        this method for each of its (at most two) attempts.
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
                    raise GmailApiError(f"Gmail request failed: {exc}") from exc
                logger.warning(
                    "gmail.retrying_connection_error", path=path, attempt=attempt, error=str(exc)
                )
                await asyncio.sleep(_backoff_seconds(attempt, None))
                continue

            if resp.status_code not in _RETRYABLE_STATUSES or attempt >= _MAX_RETRIES:
                return resp
            logger.warning(
                "gmail.retrying_status", path=path, status=resp.status_code, attempt=attempt
            )
            await asyncio.sleep(_backoff_seconds(attempt, resp.headers.get("Retry-After")))

        assert resp is not None  # loop always assigns or raises
        return resp
