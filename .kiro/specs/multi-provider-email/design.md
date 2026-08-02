# Design: Multi-Provider Email Strategy Pattern Refactor

## 1. Architecture Overview

The refactor introduces a thin **Provider Layer** between the existing
infrastructure (DB, Celery, httpx) and the domain layer (WorkflowService,
DraftService, ReviewRepository). The domain layer only ever speaks the
`BaseEmailProvider` interface and the `NormalizedEmail` value object — it has
zero knowledge of Gmail, Graph API, or IMAP wire protocol.

```
┌─────────────────────────────────────────────────────────────────────┐
│                          API / Celery Layer                          │
│  POST /workflows/pull   pull_messages_task   GET /email/messages    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ ConnectedAccount + AsyncSession
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      WorkflowService (domain)                        │
│  pull_messages()  run_message()  approve()  reject()  send()        │
│  ── only imports BaseEmailProvider + NormalizedEmail ──             │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ get_email_provider(account, session)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Provider Factory (O(1) dispatch)                │
│  app/core/email/factory.py  ──  get_email_provider()                │
└───────┬──────────────────────────┬──────────────────────────────────┘
        │ provider_type='gmail'    │ 'outlook'        │ 'imap_smtp'
        ▼                          ▼                   ▼
┌──────────────┐  ┌───────────────────┐  ┌─────────────────────────┐
│ GmailProvider│  │ MSGraphProvider   │  │   ImapSmtpProvider      │
│ (gmail.py)   │  │ (outlook.py)      │  │   (imap_smtp.py)        │
│              │  │                   │  │                         │
│ httpx +      │  │ httpx +           │  │ aioimaplib +            │
│ Gmail REST   │  │ Graph REST (stub) │  │ aiosmtplib              │
└──────┬───────┘  └────────┬──────────┘  └───────────┬─────────────┘
       │                   │                          │
       └───────────────────┴──────────────────────────┘
                           │  All return NormalizedEmail
                           ▼
              app/schemas/email.py :: NormalizedEmail
```

---

## 2. Module & File Map

```
backend/app/
├── core/
│   └── email/                        ← NEW package
│       ├── __init__.py               ← re-exports BaseEmailProvider, get_email_provider
│       ├── base.py                   ← ABC + shared exceptions + NormalizedEmail import
│       ├── factory.py                ← get_email_provider() dispatch function
│       ├── gmail.py                  ← GmailProvider (migrated from GmailService)
│       ├── outlook.py                ← MSGraphProvider (stub)
│       └── imap_smtp.py              ← ImapSmtpProvider (aioimaplib + aiosmtplib)
│
├── schemas/
│   └── email.py                      ← NEW — NormalizedEmail Pydantic model
│
├── models/
│   └── connected_account.py          ← NEW — replaces GoogleCredential as primary store
│
├── repositories/
│   └── connected_account.py          ← NEW — CRUD + list_connected_user_ids()
│
├── services/
│   └── workflow_service.py           ← MODIFIED — provider-agnostic, injects BaseEmailProvider
│
├── tasks/
│   └── workflow_tasks.py             ← MODIFIED — uses ConnectedAccount fan-out
│
├── api/
│   ├── email/                        ← NEW — provider-agnostic API surface
│   │   └── __init__.py
│   ├── gmail/
│   │   └── __init__.py               ← UNCHANGED (backwards compat shim)
│   └── auth/
│       └── routes.py                 ← MODIFIED — add POST /auth/imap/connect
│
└── alembic/versions/
    └── 0013_connected_accounts.py    ← NEW migration (additive + data migration)
```

---

## 3. Class Hierarchy

### 3.1 BaseEmailProvider (Strategy interface)

```python
# app/core/email/base.py
from abc import ABC, abstractmethod
from app.schemas.email import NormalizedEmail


class EmailProviderError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class EmailProviderNotConnectedError(EmailProviderError):
    """Account has no valid credentials stored."""


class BaseEmailProvider(ABC):

    @abstractmethod
    async def fetch_messages(
        self,
        history_id: str | None = None,
        *,
        max_results: int = 25,
        query: str | None = None,
    ) -> tuple[list[NormalizedEmail], str | None]:
        """Return (messages, new_cursor).

        ``history_id`` is the provider's opaque incremental-sync cursor
        (Gmail historyId, Graph deltaLink, IMAP UIDNEXT).  Returns a
        fresh cursor alongside the messages so callers can persist it.
        """

    @abstractmethod
    async def get_message(self, message_id: str) -> NormalizedEmail:
        """Fetch and normalise a single message by provider ID."""

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
        """Create a draft in the provider's Drafts folder.
        Returns the provider draft ID."""

    @abstractmethod
    async def send_draft(self, draft_id: str) -> str:
        """Send an existing provider draft. Returns sent message ID."""

    @abstractmethod
    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        thread_id: str | None = None,
    ) -> str:
        """Send a new email directly (no intermediate draft). Returns message ID."""
```

### 3.2 GmailProvider

```python
# app/core/email/gmail.py
class GmailProvider(BaseEmailProvider):
    """Wraps the existing Gmail REST logic from GmailService.

    Constructed by the factory; holds a reference to the ConnectedAccount
    row (contains encrypted tokens) and an AsyncSession for token persistence.
    """

    def __init__(
        self,
        account: ConnectedAccount,
        session: AsyncSession,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None: ...

    # --- all five abstract methods implemented ---
    # fetch_messages  → delegates to _list_new_messages() + _get_message()
    # get_message     → metadata-first fetch, noise detection, full body
    # create_draft    → MIME-encode, POST /drafts
    # send_draft      → POST /drafts/send
    # send_email      → POST /messages/send (raw MIME)

    # --- private helpers (ported from GmailService) ---
    # _access_token, _is_expired, _require_credential
    # _get, _post, _send_with_retry (backoff/retry unchanged)
    # _collect_bodies, _extract_body, _decode_body (MIME utils unchanged)
```

Key difference from `GmailService`: `get_message` and `fetch_messages` return
`NormalizedEmail` instead of raw `dict`. The mapping is:

| `GmailService` dict key | `NormalizedEmail` field |
|---|---|
| `msg["id"]` | `external_message_id` |
| `msg["thread_id"]` | `external_thread_id` |
| `msg["from"]` | `sender` |
| `msg["to"]` | `recipients[0]` |
| `msg["subject"]` | `subject` |
| `msg["body"] or msg["snippet"]` | `body_text` |
| `msg["date"]` (parsed to UTC) | `received_at` |
| `msg["message_id_header"]` | `message_id_header` |
| `msg["is_noise"]` | `is_noise` |
| `headers dict` | `raw_headers` |

### 3.3 MSGraphProvider (stub)

```python
# app/core/email/outlook.py
class MSGraphProvider(BaseEmailProvider):
    """Microsoft Graph API provider — stub implementation.

    Concrete methods raise NotImplementedError with an informative message
    until the OAuth callback and token exchange are wired.  The class IS
    importable and instantiable so the factory works in all environments.
    """
    GRAPH_BASE = "https://graph.microsoft.com/v1.0"

    async def fetch_messages(self, history_id=None, *, max_results=25, query=None):
        # stub: GET /me/messages?$top=N&$filter=...&$deltaToken=...
        raise NotImplementedError("MSGraphProvider.fetch_messages: Outlook not yet integrated")

    # ... other methods raise NotImplementedError similarly
```

### 3.4 ImapSmtpProvider

```python
# app/core/email/imap_smtp.py
class ImapSmtpProvider(BaseEmailProvider):
    """IMAP (fetch/draft) + SMTP (send) for Zimbra and generic mail servers.

    Uses aioimaplib for fully-async IMAP; aiosmtplib for async SMTP.
    IMAP connection is opened per-operation (stateless) — not kept alive
    across requests to avoid idle-timeout issues on corporate servers.
    """

    def __init__(self, account: ConnectedAccount) -> None:
        self._account = account
        # Lazily imported so aiosmtplib/aioimaplib are optional dependencies
        # in environments that only use Gmail or Outlook.

    async def fetch_messages(self, history_id=None, *, max_results=25, query=None):
        # IMAP SEARCH UNSEEN (or UID > last_uid cursor)
        # Maps RFC822 envelope headers to NormalizedEmail

    async def get_message(self, message_id: str) -> NormalizedEmail:
        # IMAP FETCH by UID; decodes MIME tree

    async def create_draft(self, to, subject, body, *, thread_id=None, in_reply_to=None) -> str:
        # IMAP APPEND to "Drafts" folder; returns UID as draft_id

    async def send_draft(self, draft_id: str) -> str:
        # IMAP FETCH draft by UID, SMTP SEND, IMAP STORE \Deleted on draft

    async def send_email(self, to, subject, body, *, thread_id=None) -> str:
        # Pure SMTP send; returns Message-ID header value
```

### 3.5 Factory

```python
# app/core/email/factory.py
_PROVIDER_MAP: dict[str, type[BaseEmailProvider]] = {
    "gmail":      GmailProvider,
    "outlook":    MSGraphProvider,
    "imap_smtp":  ImapSmtpProvider,
}

def get_email_provider(
    account: ConnectedAccount,
    session: AsyncSession,
    http_client: httpx.AsyncClient | None = None,
) -> BaseEmailProvider:
    cls = _PROVIDER_MAP.get(account.provider_type)
    if cls is None:
        raise ValueError(f"Unknown provider_type: {account.provider_type!r}")
    # ImapSmtpProvider doesn't use session/http_client — handled via **kwargs pattern
    return cls(account, session, http_client=http_client)
```

---

## 4. Data Model

### 4.1 ConnectedAccount (new table)

```
Table: connected_accounts
─────────────────────────────────────────────────────────────
id                UUID        PK
user_id           UUID        FK → users.id  ON DELETE CASCADE
                              UNIQUE INDEX
provider_type     VARCHAR(20) NOT NULL  CHECK IN ('gmail','outlook','imap_smtp')
provider_email    VARCHAR(320) NOT NULL
provider_sub      VARCHAR(255) NULL
access_token_enc  TEXT        NOT NULL
refresh_token_enc TEXT        NULL
token_expiry      TIMESTAMPTZ NULL
scopes            TEXT        NOT NULL  DEFAULT ''
history_id        VARCHAR(64) NULL
imap_host         VARCHAR(255) NULL
imap_port         INTEGER     NULL
smtp_host         VARCHAR(255) NULL
smtp_port         INTEGER     NULL
imap_username     VARCHAR(320) NULL
imap_password_enc TEXT        NULL
created_at        TIMESTAMPTZ NOT NULL  DEFAULT now()
updated_at        TIMESTAMPTZ NOT NULL  DEFAULT now()
─────────────────────────────────────────────────────────────
```

### 4.2 DraftReview column aliases

The existing columns are renamed in the migration; SQLAlchemy models expose
both the new canonical name and a `synonym` under the old name for the
transition period:

| Old column | New column | Notes |
|---|---|---|
| `gmail_message_id` | `provider_message_id` | Keep old name as synonym |
| `gmail_thread_id` | `provider_thread_id` | Keep old name as synonym |
| `gmail_draft_id` | `provider_draft_id` | Keep old name as synonym |

The `UniqueConstraint("user_id", "gmail_message_id")` is recreated as
`("user_id", "provider_message_id")` in the migration.

### 4.3 Entity Relationship (simplified)

```
users (1) ──────────────── (0..1) connected_accounts
                                      │ provider_type ∈ {'gmail','outlook','imap_smtp'}
users (1) ──────────────── (0..1) google_credentials   ← LEGACY (not dropped)

users (1) ──────────────── (*) draft_reviews
                                      │ provider_message_id
                                      │ provider_thread_id
                                      │ provider_draft_id
```

---

## 5. WorkflowService Refactor

### 5.1 New constructor signature

```python
class WorkflowService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        ai: AIClient | None = None,
        email_provider: BaseEmailProvider | None = None,  # NEW — injectable
    ) -> None:
        self.session = session
        self.repo = DraftReviewRepository(session)
        self.triage = TriageService(ai)
        self.draft = DraftService(session, ai)
        self._email_provider = email_provider  # resolved lazily if None
```

The provider is resolved lazily on first access via a private helper so that
code paths that don't touch email (e.g. `reject()`) pay zero cost:

```python
    def _provider(self, account: ConnectedAccount) -> BaseEmailProvider:
        if self._email_provider is not None:
            return self._email_provider
        return get_email_provider(account, self.session)
```

### 5.2 pull_messages replaces pull_gmail

```python
async def pull_messages(
    self,
    user: User,
    account: ConnectedAccount,
    *,
    max_results: int = 12,
    query: str | None = None,
) -> dict[str, int]:
    provider = self._provider(account)
    messages, new_cursor = await provider.fetch_messages(
        history_id=account.history_id,
        max_results=max_results,
        query=query,
    )
    if new_cursor:
        await ConnectedAccountRepository(self.session).update_history_id(
            account, history_id=new_cursor
        )
    # dedup + per-message pipeline (same as pull_gmail, but msg is NormalizedEmail)
    ...
```

### 5.3 run_message replaces run_gmail

```python
async def run_message(
    self,
    user: User,
    account: ConnectedAccount,
    message: NormalizedEmail,     # already fetched by pull_messages
) -> DraftReview:
    subject = message.subject
    body    = message.body_text or message.raw_headers.get("snippet", "")

    if message.is_noise:
        triage = { "intent": "irrelevant", ... }
    else:
        triage = await self.triage.classify(subject, body)

    # ... safety gate, draft generation — identical logic, no Gmail references ...

    review = await self.repo.create(
        user_id=user.id,
        provider_message_id=message.external_message_id,   # NEW field name
        provider_thread_id=message.external_thread_id,
        message_id_header=message.message_id_header,
        sender=message.sender,
        ...
    )
    return review
```

### 5.4 approve / send

```python
async def approve(self, user: User, account: ConnectedAccount, review: DraftReview):
    provider = self._provider(account)
    ...
    pushed_draft_id = await provider.create_draft(
        to=claimed.sender,
        subject=reply_subject,
        body=claimed.draft_body,
        thread_id=claimed.provider_thread_id or None,
        in_reply_to=claimed.message_id_header or None,
    )
    await self.repo.mark_approved(claimed, provider_draft_id=pushed_draft_id, ...)

async def send(self, user: User, account: ConnectedAccount, review: DraftReview):
    provider = self._provider(account)
    sent_id = await provider.send_draft(claimed.provider_draft_id or "")
    ...
```

---

## 6. Celery Task Refactor

### 6.1 New task structure

```
workflow.pull_messages        (renamed from workflow.pull_gmail)
    ├── arg: user_id: str
    ├── arg: account_id: str   (ConnectedAccount UUID)
    ├── retries: 3, delay: 30s
    └── _RETRYABLE_ERRORS: EmailProviderError, AIError

workflow.pull_gmail            (alias — same function, deprecated name)
    └── delegates to pull_messages_task(user_id, ...)

workflow.pull_all_connected    (fan-out Beat task)
    └── queries ConnectedAccount (all provider types, not just GoogleCredential)
        └── dispatches pull_messages_task per account
```

### 6.2 _pull_messages_async

```python
async def _pull_messages_async(
    user_id: str,
    account_id: str,
    max_results: int,
    query: str | None,
    *,
    session_factory=AsyncSessionLocal,
) -> dict:
    async with session_factory() as session:
        user    = await UserRepository(session).get_by_id(UUID(user_id))
        account = await ConnectedAccountRepository(session).get_by_id(UUID(account_id))
        if user is None or account is None:
            raise ValueError(...)
        return await WorkflowService(session).pull_messages(
            user, account, max_results=max_results, query=query
        )
```

### 6.3 Beat schedule update

```python
# app/workers/celery_app.py
beat_schedule = {
    "email-auto-pull": {
        "task": "workflow.pull_all_connected",   # unchanged task name
        "schedule": settings.gmail_auto_pull_interval_seconds,
    }
}
```

The Beat task name stays the same; only its implementation queries
`ConnectedAccount` instead of `GoogleCredential`.

---

## 7. API Layer Changes

### 7.1 New /email/* routes

```
GET  /api/v1/email/connection
     → ConnectedAccountRepository.get_by_user_id(user)
     ← { provider_type, provider_email, connected, history_id }

GET  /api/v1/email/messages?max_results=N
     → get_email_provider(account) → fetch_messages()
     ← [ NormalizedEmail, ... ]

POST /api/v1/email/drafts
     body: { to, subject, body, thread_id? }
     → get_email_provider(account) → create_draft()
     ← { draft_id }
```

### 7.2 IMAP/SMTP connect endpoint

```
POST /api/v1/auth/imap/connect
     body: {
       imap_host, imap_port,
       smtp_host, smtp_port,
       username, password       ← encrypted before storage
     }
     → validates host/port allowlist
     → crypto.encrypt(password) → ConnectedAccount(provider_type='imap_smtp')
     ← 201 { connected: true, provider_email: username }
```

### 7.3 Gmail routes — backwards compatibility

`app/api/gmail/__init__.py` is NOT modified in the first pass. The existing
five endpoints continue to instantiate `GmailService` (which remains as a
compatibility shim calling through to `GmailProvider` internally) until the
frontend migrates to `/email/*`. A follow-up PR will deprecate and remove them.

---

## 8. Alembic Migration Design

### Migration: 0013_connected_accounts.py

**Upgrade steps (in order):**

1. `CREATE TABLE connected_accounts` (all columns from §4.1)
2. `INSERT INTO connected_accounts SELECT ...` from `google_credentials`
   (maps `google_sub → provider_sub`, `google_email → provider_email`,
   `provider_type = 'gmail'`, all token ciphertext columns copied verbatim)
3. `ALTER TABLE draft_reviews RENAME COLUMN gmail_message_id TO provider_message_id`
4. `ALTER TABLE draft_reviews RENAME COLUMN gmail_thread_id  TO provider_thread_id`
5. `ALTER TABLE draft_reviews RENAME COLUMN gmail_draft_id   TO provider_draft_id`
6. `DROP CONSTRAINT uq_draft_reviews_user_gmail_message`
7. `ADD CONSTRAINT uq_draft_reviews_user_provider_message UNIQUE (user_id, provider_message_id)`

**Downgrade steps (in reverse order):**

1. Drop `uq_draft_reviews_user_provider_message`
2. Rename columns back (`provider_*` → `gmail_*`)
3. Add `uq_draft_reviews_user_gmail_message`
4. `DROP TABLE connected_accounts`

> **Safety note:** `google_credentials` is NOT dropped in this migration.
> Steps 3–7 are the only mutation of existing data; they are pure renames with
> no data loss. The INSERT in step 2 is idempotent when re-run (ON CONFLICT DO
> NOTHING).

---

## 9. Dependency Additions

| Package | Version pin | Purpose | Install condition |
|---|---|---|---|
| `aioimaplib` | `>=1.1.0,<2` | Async IMAP client | Always (optional import) |
| `aiosmtplib` | `>=3.0.0,<4` | Async SMTP client | Always (optional import) |
| `msal` | `>=1.31.0,<2` | MS Entra/Azure AD token exchange | Optional, lazy import |

All three are lazily imported inside their respective provider files so that
environments without them (Gmail-only deploys) never see an `ImportError` at
startup. A `try/except ImportError` block in each provider raises a clear
`RuntimeError("Install aioimaplib to use IMAP/SMTP provider")` on first use.

---

## 10. Error Handling & Observability

### 10.1 Exception mapping

Each provider translates its native exceptions to the two standard ones:

| Provider | Native exception | Maps to |
|---|---|---|
| Gmail | `GmailNotConnectedError` | `EmailProviderNotConnectedError` |
| Gmail | `GmailApiError` | `EmailProviderError(status_code=...)` |
| MSGraph | `httpx.HTTPStatusError` (401) | `EmailProviderNotConnectedError` |
| MSGraph | `httpx.HTTPStatusError` (4xx/5xx) | `EmailProviderError` |
| IMAP/SMTP | `aioimaplib.Abort` | `EmailProviderError` |
| IMAP/SMTP | `aiosmtplib.SMTPException` | `EmailProviderError` |

### 10.2 Structured logging

All provider operations emit structured log events under the
`email_provider.*` namespace, including `provider_type` so logs are
filterable:

```
email_provider.fetch_messages  provider_type=gmail  count=5  cursor_advanced=true
email_provider.get_message     provider_type=gmail  message_id=...  is_noise=false
email_provider.create_draft    provider_type=imap_smtp  to=...
email_provider.error           provider_type=outlook  status_code=429  retrying=true
```

### 10.3 Celery retries

`EmailProviderError` is added to `_RETRYABLE_ERRORS` in `workflow_tasks.py`
alongside `AIError`. `EmailProviderNotConnectedError` and `ValueError` remain
permanent failures (no retry).

---

## 11. Testing Strategy

### 11.1 Unit tests — providers

Each provider is tested with injected fakes:
- `GmailProvider`: inject `httpx.MockTransport` (same pattern as existing
  `GmailService` tests)
- `MSGraphProvider`: inject `httpx.MockTransport`; assert `NotImplementedError`
  on all methods until stubs are replaced
- `ImapSmtpProvider`: use `aioimaplib`'s built-in test server or a mock `asyncio`
  transport

### 11.2 Unit tests — factory

```python
def test_factory_returns_gmail_provider():
    account = ConnectedAccount(provider_type="gmail", ...)
    provider = get_email_provider(account, mock_session)
    assert isinstance(provider, GmailProvider)

def test_factory_raises_on_unknown():
    account = ConnectedAccount(provider_type="fax", ...)
    with pytest.raises(ValueError, match="Unknown provider_type"):
        get_email_provider(account, mock_session)
```

### 11.3 Integration tests — WorkflowService

Existing `WorkflowService` tests inject a `FakeEmailProvider(BaseEmailProvider)`
that returns canned `NormalizedEmail` objects. This replaces the current
`httpx.MockTransport` setup and makes tests provider-agnostic.

### 11.4 Migration tests

A `pytest` fixture runs `alembic upgrade 0013` and `alembic downgrade 0012`
against a throwaway SQLite DB seeded with a `google_credentials` row, asserting
that `connected_accounts` contains a matching row post-upgrade and the
`draft_reviews` column rename is reversible.

---

## 12. Rollout Plan

| Phase | Scope | Risk |
|---|---|---|
| **P0** — Schema + abstractions | `NormalizedEmail`, `BaseEmailProvider`, `ConnectedAccount` model, migration | Low — additive only |
| **P1** — GmailProvider | Port `GmailService` → `GmailProvider`; update `WorkflowService` + tasks | Medium — touches hot path |
| **P2** — API layer | New `/email/*` routes; `WorkflowService.approve/send` via provider | Medium |
| **P3** — ImapSmtpProvider | Full IMAP/SMTP implementation; `POST /auth/imap/connect` | Medium |
| **P4** — MSGraphProvider | Outlook OAuth callback, token exchange, full Graph implementation | High — new OAuth flow |
| **P5** — Cleanup | Remove `GmailService`, deprecate `/gmail/*` routes, drop `google_credentials` table | Low — deferred |

Each phase is independently deployable. The existing Gmail flow is unaffected
until P1 is deployed; P1 is the only phase with a breaking internal change
(WorkflowService constructor), but because `email_provider` defaults to `None`
(lazy resolution), existing call sites that pass no provider continue to work.
