# Requirements: Multi-Provider Email Strategy Pattern Refactor

## Overview

The current backend is tightly coupled to Gmail via `GmailService` (using direct
httpx calls against the Gmail REST API) and `GoogleCredential` (a one-to-one
user-credential table). All workflow orchestration in `WorkflowService`,
every Celery task in `workflow_tasks.py`, and the human-in-the-loop review
lifecycle (`approve`, `send`) call Gmail-specific methods directly.

This refactor introduces the **Strategy Pattern** so that the core pipeline
(triage → draft → review → approve → send) is entirely agnostic of the
underlying email transport. Gmail becomes one of several concrete providers
alongside Microsoft Graph (Outlook) and generic IMAP/SMTP (Zimbra, etc.).

---

## Actors & Scope

| Actor | Description |
|---|---|
| Clinic Staff | Connects their email account (Gmail / Outlook / Zimbra) to the system |
| System (Celery) | Periodically pulls new messages via the correct provider for each connected account |
| AI Pipeline | Receives `NormalizedEmail` objects; has no knowledge of provider mechanics |
| Admin | May configure shared-inbox credentials for IMAP/SMTP accounts |

---

## Functional Requirements

### FR-1  Unified Email Provider Interface

**FR-1.1** The system MUST define an abstract base class `BaseEmailProvider` in
`app/core/email/base.py` with the following async contract:

```
fetch_messages(history_id: str | None = None) -> list[NormalizedEmail]
send_email(to, subject, body, thread_id=None) -> str          # returns provider message ID
create_draft(to, subject, body, thread_id=None) -> str        # returns provider draft ID
send_draft(draft_id: str) -> str                              # returns sent message ID
get_message(message_id: str) -> NormalizedEmail
```

**FR-1.2** All concrete providers MUST inherit from `BaseEmailProvider` and
implement every abstract method. Failing to implement any method MUST raise
`NotImplementedError` at class-definition time (enforced by `abc.ABC`).

**FR-1.3** Providers MUST raise only the two standardised exceptions defined in
`app/core/email/base.py`:
- `EmailProviderNotConnectedError` — account has no valid credentials
- `EmailProviderError` — any provider-level API/network failure (wraps the
  original exception and exposes `status_code: int | None`)

**FR-1.4** All provider methods MUST be `async`-native. Blocking I/O
(e.g., standard-library `imaplib`) MUST be wrapped with
`asyncio.get_event_loop().run_in_executor`.

---

### FR-2  NormalizedEmail Schema

**FR-2.1** Define a Pydantic model `NormalizedEmail` in `app/schemas/email.py`:

| Field | Type | Description |
|---|---|---|
| `provider_type` | `Literal['gmail','outlook','imap_smtp']` | Source provider |
| `external_message_id` | `str` | Provider's opaque message identifier |
| `external_thread_id` | `str` | Provider's thread/conversation identifier (empty string if unsupported) |
| `sender` | `str` | RFC 5322 From address |
| `recipients` | `list[str]` | To addresses |
| `subject` | `str` | Decoded subject line |
| `body_text` | `str` | Plain-text body (HTML stripped as fallback) |
| `received_at` | `datetime` | UTC-normalised received timestamp |
| `message_id_header` | `str` | RFC 2822 `Message-ID` header (for reply threading) |
| `is_noise` | `bool` | Provider-side noise classification (spam, sent, draft) |
| `raw_headers` | `dict[str, str]` | Original provider headers (for debugging) |

**FR-2.2** `NormalizedEmail` MUST be immutable (`model_config = ConfigDict(frozen=True)`).

**FR-2.3** Existing code that reads `msg["subject"]`, `msg["from"]`, `msg["body"]`,
`msg["id"]`, `msg["thread_id"]`, `msg["is_noise"]` from `GmailService.get_message`
MUST be migrated to read the equivalent `NormalizedEmail` fields.

---

### FR-3  ConnectedAccount Data Model

**FR-3.1** Introduce a new DB model `ConnectedAccount` in
`app/models/connected_account.py` to replace `GoogleCredential` as the
canonical credential store. One `User` may have **one ConnectedAccount**
(unique constraint on `user_id`) — the existing 1:1 pattern is preserved.

**FR-3.2** `ConnectedAccount` MUST store the following columns:

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID PK | No | |
| `user_id` | UUID FK → users | No | Unique, indexed |
| `provider_type` | VARCHAR(20) | No | `'gmail'`, `'outlook'`, `'imap_smtp'` |
| `provider_email` | VARCHAR(320) | No | The connected mailbox address |
| `provider_sub` | VARCHAR(255) | Yes | Provider's stable account identifier (Google `sub`, Entra OID) |
| `access_token_enc` | Text | No | Fernet-encrypted access token |
| `refresh_token_enc` | Text | Yes | Fernet-encrypted refresh token |
| `token_expiry` | DateTime(tz) | Yes | UTC expiry of access token |
| `scopes` | Text | No | Space-separated granted scopes |
| `history_id` | VARCHAR(64) | Yes | Incremental sync cursor (Gmail historyId / Graph deltaToken) |
| `imap_host` | VARCHAR(255) | Yes | IMAP server hostname (IMAP/SMTP only) |
| `imap_port` | Integer | Yes | IMAP port (default 993) |
| `smtp_host` | VARCHAR(255) | Yes | SMTP server hostname (IMAP/SMTP only) |
| `smtp_port` | Integer | Yes | SMTP port (default 587) |
| `imap_username` | VARCHAR(320) | Yes | IMAP login username if different from email |
| `imap_password_enc` | Text | Yes | Fernet-encrypted IMAP/SMTP password |

**FR-3.3** `GoogleCredential` MUST remain in place until the Alembic migration has
back-filled `ConnectedAccount` rows, then be soft-deprecated (not dropped in this
refactor — saved for a follow-up cleanup migration).

**FR-3.4** The Alembic migration MUST include a data-migration step that copies
all existing `google_credentials` rows into `connected_accounts` with
`provider_type = 'gmail'`, preserving encrypted token ciphertext byte-for-byte
so no re-encryption is required.

---

### FR-4  Provider Implementations

**FR-4.1 — GmailProvider**
- Located at `app/core/email/gmail.py`
- Wraps the existing `GmailService` logic (httpx, token refresh, retry/backoff,
  incremental history via `history_id`, noise-label filtering)
- Accepts a `ConnectedAccount` (provider_type = 'gmail') and `AsyncSession`
- All existing Gmail behaviour (incremental sync, backoff, draft threading) MUST
  be preserved
- Returns `NormalizedEmail` objects from `get_message` and `fetch_messages`

**FR-4.2 — MSGraphProvider (stub)**
- Located at `app/core/email/outlook.py`
- Implements all five `BaseEmailProvider` methods
- `fetch_messages` calls `GET /v1.0/me/messages` with a `$filter` and `$top`
- All methods raise `NotImplementedError` with a `"Outlook integration coming soon"`
  message until fully implemented — OR return empty/mock results in non-production
  environments; the stub MUST NOT break the factory or app startup
- Stores `deltaLink` in `history_id` for incremental sync (MS Graph delta query
  pattern)

**FR-4.3 — ImapSmtpProvider**
- Located at `app/core/email/imap_smtp.py`
- Uses `aioimaplib` for async IMAP fetch (SSL/STARTTLS)
- Uses `aiosmtplib` for async SMTP send
- `fetch_messages`: searches UNSEEN messages; filters noise (SPAM, SENT flags)
- `create_draft`: appends to the `Drafts` folder via IMAP APPEND
- `send_email`: sends via SMTP directly (no draft intermediate step)
- `send_draft`: fetches draft from Drafts folder, sends via SMTP, moves to Sent
- Credentials come from `imap_host`, `imap_port`, `smtp_host`, `smtp_port`,
  `imap_username`, and decrypted `imap_password_enc` on `ConnectedAccount`

---

### FR-5  Provider Factory

**FR-5.1** A module-level function `get_email_provider` in
`app/core/email/factory.py` MUST return the correct `BaseEmailProvider` subclass
based on `account.provider_type`.

**FR-5.2** Passing an unrecognised `provider_type` MUST raise `ValueError`
immediately (fail-fast, not silent).

**FR-5.3** The factory signature MUST be:
```python
def get_email_provider(
    account: ConnectedAccount,
    session: AsyncSession,
    http_client: httpx.AsyncClient | None = None,
) -> BaseEmailProvider
```
The optional `http_client` parameter allows tests to inject mock transports
without monkeypatching.

---

### FR-6  Workflow & Celery Integration

**FR-6.1** `WorkflowService` MUST be refactored so that `pull_gmail`, `run_gmail`,
`approve`, and `send` no longer import or instantiate `GmailService` directly.
Instead they MUST obtain a provider instance via `get_email_provider`.

**FR-6.2** A generic `pull_messages` method MUST replace `pull_gmail` on
`WorkflowService`, accepting a `ConnectedAccount` instead of a raw `User`
and a `BaseEmailProvider` (injected, not resolved internally) to keep it testable.

**FR-6.3** The Celery task `workflow.pull_gmail` MUST be renamed to
`workflow.pull_messages` with a backwards-compatible alias so existing Beat
schedules and in-flight tasks do not fail during a rolling deployment.

**FR-6.4** `pull_all_connected_task` MUST be updated to fan out across
`ConnectedAccount` rows (all provider types) instead of only `GoogleCredential`
rows.

**FR-6.5** The `DraftReview` model columns `gmail_message_id`, `gmail_thread_id`,
and `gmail_draft_id` MUST be aliased to provider-agnostic names
(`provider_message_id`, `provider_thread_id`, `provider_draft_id`) via
SQLAlchemy `synonym` or a migration rename, preserving existing data.

---

### FR-7  API Routes

**FR-7.1** The existing `/api/v1/gmail/*` routes MUST continue to work unchanged
(backwards compatibility for the current frontend).

**FR-7.2** New provider-agnostic routes MUST be added under
`/api/v1/email/*`:
- `GET /email/connection` — returns provider type, email, connection status
- `GET /email/messages` — lists recent messages (delegates to active provider)
- `POST /email/drafts` — create a draft reply (delegates to active provider)

**FR-7.3** IMAP/SMTP connection setup (Zimbra) MUST have its own setup endpoint
under `POST /api/v1/auth/imap/connect` accepting host/port/username/password.

---

### FR-8  Configuration

**FR-8.1** Add the following optional settings to `app/core/config.py`:
- `outlook_client_id: str = ""`
- `outlook_client_secret: SecretStr = SecretStr("")`
- `outlook_tenant_id: str = "common"`
- `outlook_redirect_uri: str = ""`
- `imap_default_port: int = 993`
- `smtp_default_port: int = 587`

**FR-8.2** Computed fields `outlook_configured: bool` and
`imap_smtp_configured: bool` MUST be added following the same pattern as
`google_oauth_configured`.

---

### FR-9  Security

**FR-9.1** IMAP passwords MUST be encrypted with the existing Fernet key
(`TOKEN_ENCRYPTION_KEY`) before storage, using the same `crypto.encrypt` /
`crypto.decrypt` utilities as Gmail tokens.

**FR-9.2** No provider credential (token, password) MUST ever appear in
application logs, Celery task arguments, or API responses.

**FR-9.3** IMAP/SMTP host and port values supplied by users at connection time
MUST be validated against an allowlist of safe ports (993, 143, 587, 465, 25)
and a hostname format check before being persisted.

---

### FR-10  Backwards Compatibility & Migration Safety

**FR-10.1** The Alembic migration MUST be reversible (`downgrade` defined and
tested locally).

**FR-10.2** Gmail tokens already encrypted in `google_credentials` MUST survive
the migration intact — the ciphertext is copied as-is, no re-encryption.

**FR-10.3** All existing `DraftReview` rows referencing Gmail message IDs MUST
remain valid after any column rename (accomplished via `ALTER COLUMN ... RENAME`
plus a SQLAlchemy property alias, not a data wipe).

**FR-10.4** During the migration window both `GmailService` (legacy) and
`GmailProvider` (new) MUST be able to decrypt the same ciphertext without
modification, since the underlying `crypto` module is shared.

---

## Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | No provider-specific import MAY appear in `workflow_service.py`, `workflow_tasks.py`, or `draft_review` repository after the refactor |
| NFR-2 | Each provider class MUST be independently unit-testable with no real network calls (injectable `http_client` / fake IMAP server) |
| NFR-3 | The factory `get_email_provider` MUST resolve in O(1) — no DB calls |
| NFR-4 | Adding a fourth provider in the future MUST require changes only to: the new provider file, `factory.py`, and the Alembic migration — nothing else |
| NFR-5 | Existing test suite MUST pass without modification after the refactor (public `GmailService` interface preserved as a shim until tests are migrated) |
| NFR-6 | The `MSGraphProvider` stub MUST be importable and instantiable without MSAL installed (lazy import with a clear `ImportError` message) |

---

## Out of Scope (this refactor)

- Full Outlook OAuth callback flow (FR-4.2 stub only)
- Sending email via Outlook or IMAP in production (stubs accepted)
- Multi-account per user (the 1:1 constraint is preserved)
- Frontend changes beyond what is needed to surface the new `/email/*` endpoints
- Removing `GoogleCredential` table (deferred to cleanup migration)
