"""Gmail access for the shared clinical inbox (Phase 2).

Wraps the Gmail REST API with ``httpx`` (async). Handles transparent access-token
refresh using the stored (encrypted) refresh token. Reads messages (gmail.readonly)
and creates reply *drafts* (gmail.compose) — it never sends mail automatically;
a human reviews and sends every draft from Gmail.
"""

from __future__ import annotations

import base64
import datetime as dt
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
        cred = await self._require_credential(user)
        # ``full`` returns the complete MIME payload so we can extract the body,
        # not just the truncated snippet.
        params = {"format": "full"}
        data = await self._get(cred, f"/users/{self.mailbox}/messages/{message_id}", params=params)
        payload = data.get("payload", {})
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
        return {
            "id": data.get("id", message_id),
            "thread_id": data.get("threadId", ""),
            "snippet": data.get("snippet", ""),
            "body": _extract_body(payload),
            "subject": headers.get("subject", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "date": headers.get("date", ""),
            # RFC822 Message-ID header — used to thread reply drafts correctly.
            "message_id_header": headers.get("message-id", ""),
            "label_ids": data.get("labelIds", []),
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

    # --- low-level GET with one refresh-retry on 401 ----------------------

    async def _get(self, cred: GoogleCredential, path: str, *, params: dict) -> dict:
        async with self._http() as client:
            token = await self._access_token(cred, client)
            resp = await self._do_get(client, path, params, token)

            if resp.status_code == httpx.codes.UNAUTHORIZED and cred.refresh_token_enc:
                # Token may have been revoked/expired early; force one refresh + retry.
                refresh_token = crypto.decrypt(cred.refresh_token_enc)
                tokens = await google_oauth.refresh_access_token(refresh_token, client=client)
                await self.repo.update_access_token(
                    cred,
                    access_token_enc=crypto.encrypt(tokens.access_token),
                    token_expiry=tokens.expiry,
                )
                resp = await self._do_get(client, path, params, tokens.access_token)

        if resp.status_code != httpx.codes.OK:
            raise GmailApiError(f"Gmail API {resp.status_code}: {resp.text}")
        return resp.json()

    @staticmethod
    async def _do_get(
        client: httpx.AsyncClient, path: str, params: dict, token: str
    ) -> httpx.Response:
        try:
            return await client.get(
                f"{GMAIL_BASE}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            raise GmailApiError(f"Gmail request failed: {exc}") from exc

    # --- low-level POST with one refresh-retry on 401 ---------------------

    async def _post(self, cred: GoogleCredential, path: str, *, json: dict) -> dict:
        async with self._http() as client:
            token = await self._access_token(cred, client)
            resp = await self._do_post(client, path, json, token)

            if resp.status_code == httpx.codes.UNAUTHORIZED and cred.refresh_token_enc:
                refresh_token = crypto.decrypt(cred.refresh_token_enc)
                tokens = await google_oauth.refresh_access_token(refresh_token, client=client)
                await self.repo.update_access_token(
                    cred,
                    access_token_enc=crypto.encrypt(tokens.access_token),
                    token_expiry=tokens.expiry,
                )
                resp = await self._do_post(client, path, json, tokens.access_token)

        if resp.status_code not in (httpx.codes.OK, httpx.codes.CREATED):
            raise GmailApiError(f"Gmail API {resp.status_code}: {resp.text}")
        return resp.json()

    @staticmethod
    async def _do_post(
        client: httpx.AsyncClient, path: str, json: dict, token: str
    ) -> httpx.Response:
        try:
            return await client.post(
                f"{GMAIL_BASE}{path}",
                json=json,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            raise GmailApiError(f"Gmail request failed: {exc}") from exc
