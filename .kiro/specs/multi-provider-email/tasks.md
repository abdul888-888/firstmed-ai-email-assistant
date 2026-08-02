# Tasks: Multi-Provider Email Strategy Pattern Refactor

Ordered by the 5-phase rollout defined in `design.md`.
Each task is self-contained and independently reviewable.
Tasks within the same phase may be parallelised unless a dependency is noted.

---

## Phase 0 — Schema & Abstractions (additive only, zero risk to existing flow)

### Task 0.1 — Create `NormalizedEmail` Pydantic schema

**File:** `backend/app/schemas/email.py` (new file)

- Define `NormalizedEmail` with all fields from `requirements.md §FR-2.1`:
  `provider_type`, `external_message_id`, `external_thread_id`, `sender`,
  `recipients`, `subject`, `body_text`, `received_at`, `message_id_header`,
  `is_noise`, `raw_headers`.
- Set `model_config = ConfigDict(frozen=True)`.
- `received_at` must be `datetime` with `datetime` validator that coerces
  naive datetimes to UTC (`dt.timezone.utc`).
- `provider_type` must be `Literal["gmail", "outlook", "imap_smtp"]`.
- Add `__all__` export in `app/schemas/__init__.py` (or create it if absent).

**Acceptance criteria:**
- `from app.schemas.email import NormalizedEmail` works with no side-effects.
- `NormalizedEmail(provider_type="gmail", ...)` is hashable (frozen).
- A `NormalizedEmail` instance with a naive `received_at` raises a
  `ValidationError` (strict UTC enforcement).

---

### Task 0.2 — Create `BaseEmailProvider` ABC and shared exceptions

**File:** `backend/app/core/email/base.py` (new file)
**File:** `backend/app/core/email/__init__.py` (new file)

- Create the `app/core/email/` package with `__init__.py`.
- In `base.py` define:
  - `EmailProviderError(Exception)` with `status_code: int | None` attribute.
  - `EmailProviderNotConnectedError(EmailProviderError)`.
  - `BaseEmailProvider(ABC)` with all five abstract async methods exactly as
    specified in `design.md §3.1`.
  - `fetch_messages` returns `tuple[list[NormalizedEmail], str | None]`
    (messages, new cursor).
- Re-export `BaseEmailProvider`, `EmailProviderError`,
  `EmailProviderNotConnectedError` from `app/core/email/__init__.py`.

**Acceptance criteria:**
- `from app.core.email import BaseEmailProvider` works.
- Instantiating `BaseEmailProvider()` raises `TypeError` (ABC enforcement).
- A concrete subclass missing any method raises `TypeError` at class body time.

---

### Task 0.3 — Create `ConnectedAccount` SQLAlchemy model

**File:** `backend/app/models/connected_account.py` (new file)

- Define `ConnectedAccount(Base, TimestampMixin)` with all columns from
  `design.md §4.1`.
- `provider_type` stored as `String(20)` — NOT a SQLAlchemy `Enum` type
  (avoids a separate ALTER on future provider additions; validation is at the
  Pydantic layer).
- Add `UniqueConstraint` on `user_id` (one account per user).
- Add `Index("ix_connected_accounts_user_id", "user_id")`.
- Do NOT add a SQLAlchemy `relationship` to `User` in this task (avoids
  circular import churn; add later if needed).

**Acceptance criteria:**
- `from app.models.connected_account import ConnectedAccount` works.
- Table creation SQL (via `Base.metadata.create_all`) includes all columns
  and the unique constraint.

---

### Task 0.4 — Create `ConnectedAccountRepository`

**File:** `backend/app/repositories/connected_account.py` (new file)

Implement the following async methods (all accept `AsyncSession` in `__init__`):

| Method | Description |
|---|---|
| `get_by_user_id(user_id: UUID) -> ConnectedAccount \| None` | Lookup by user |
| `get_by_id(account_id: UUID) -> ConnectedAccount \| None` | Lookup by PK |
| `list_connected_user_ids() -> list[UUID]` | All user_ids with an account |
| `create(user_id, provider_type, provider_email, **kwargs) -> ConnectedAccount` | Insert |
| `update_history_id(account, history_id: str) -> None` | Cursor advance |
| `update_access_token(account, access_token_enc, token_expiry) -> None` | Token refresh |

- Mirror the interface of `GoogleCredentialRepository` so callers can swap
  with minimal churn.

**Acceptance criteria:**
- All methods have type annotations and docstrings.
- `list_connected_user_ids` returns only users whose account `is_active`
  (join to `users` table, filter `users.is_active = true`).

---

### Task 0.5 — Write Alembic migration `0013_connected_accounts`

**File:** `backend/alembic/versions/0013_connected_accounts.py` (new file)

Implement `upgrade()` and `downgrade()` exactly as specified in
`design.md §8`:

**upgrade:**
1. `CREATE TABLE connected_accounts` with all columns + constraints.
2. `INSERT INTO connected_accounts (id, user_id, provider_type, ...) SELECT ...`
   from `google_credentials` — map `google_sub → provider_sub`,
   `google_email → provider_email`, hardcode `provider_type = 'gmail'`.
   Use `ON CONFLICT (user_id) DO NOTHING` for idempotency.
3. Rename `draft_reviews.gmail_message_id → provider_message_id`.
4. Rename `draft_reviews.gmail_thread_id  → provider_thread_id`.
5. Rename `draft_reviews.gmail_draft_id   → provider_draft_id`.
6. Drop `uq_draft_reviews_user_gmail_message` constraint.
7. Add `uq_draft_reviews_user_provider_message` unique constraint on
   `(user_id, provider_message_id)`.

**downgrade:** exact reverse of all seven steps.

**Acceptance criteria:**
- `alembic upgrade head` followed by `alembic downgrade -1` on a DB seeded
  with at least one `google_credentials` row completes without error.
- Post-upgrade: `connected_accounts` row count equals `google_credentials`
  row count; `access_token_enc` ciphertext is byte-for-byte identical.
- Post-downgrade: `draft_reviews` columns are back to their original names.

---

## Phase 1 — GmailProvider + WorkflowService Refactor (hot path change)

> **Dependency:** Phase 0 tasks must be merged and migration applied before
> any Phase 1 code reaches a shared dev/staging DB.

---

### Task 1.1 — Implement `GmailProvider`

**File:** `backend/app/core/email/gmail.py` (new file)

Port all logic from `app/services/gmail_service.py` into `GmailProvider(BaseEmailProvider)`:

- Constructor: `__init__(self, account: ConnectedAccount, session: AsyncSession, *, http_client=None)`
- Private helpers to copy verbatim (no behaviour change):
  - `_backoff_seconds`, `_decode_body`, `_collect_bodies`, `_extract_body`
  - `_send_with_retry` (static method)
  - `_is_expired`, `_access_token` (token refresh, uses `ConnectedAccountRepository`)
  - `_get`, `_post` (low-level HTTP with one refresh-retry on 401)
- `_NOISE_LABELS`, `_METADATA_HEADERS`, retry constants — copy unchanged.
- Implement the five abstract methods:

  **`get_message(message_id) -> NormalizedEmail`**
  - Same metadata-first / full-body two-step as `GmailService.get_message`.
  - Map result dict to `NormalizedEmail` using the field mapping table in
    `design.md §3.2`. Parse `headers["date"]` → UTC `datetime`.

  **`fetch_messages(history_id, *, max_results, query) -> tuple[list[NormalizedEmail], str|None]`**
  - Encapsulates `list_new_messages` + `get_history` + `get_profile` logic.
  - Returns `(messages, new_history_id)` — does NOT write the cursor itself
    (caller does via `ConnectedAccountRepository.update_history_id`).
  - Each message ID from the listing is fetched via `get_message` and appended.

  **`create_draft(to, subject, body, *, thread_id, in_reply_to) -> str`**
  - Identical to `GmailService.create_draft`; returns `draft_id` string
    (previously returned a dict — strip to just the ID).

  **`send_draft(draft_id) -> str`**
  - Identical to `GmailService.send_draft`; returns `message_id` string.

  **`send_email(to, subject, body, *, thread_id) -> str`**
  - New method (GmailService lacked a direct send). Build raw MIME, POST to
    `/users/{mailbox}/messages/send`. Returns sent message ID.

- Map `GmailNotConnectedError` → `EmailProviderNotConnectedError`.
- Map `GmailApiError` → `EmailProviderError(status_code=...)`.

**Acceptance criteria:**
- All existing `GmailService` unit tests pass when the test subject is
  switched to `GmailProvider` (the interface is a strict superset).
- `get_message` returns a `NormalizedEmail` with `provider_type="gmail"`.
- `fetch_messages` with `history_id=None` falls back to full list + bootstraps cursor.
- Both `EmailProviderNotConnectedError` and `EmailProviderError` are raised
  (never `GmailNotConnectedError` / `GmailApiError`) from public methods.

---

### Task 1.2 — Implement `MSGraphProvider` stub

**File:** `backend/app/core/email/outlook.py` (new file)

- `MSGraphProvider(BaseEmailProvider)` constructor:
  `__init__(self, account: ConnectedAccount, session: AsyncSession, *, http_client=None)`
- All five abstract methods raise `NotImplementedError` with the message
  `"MSGraphProvider.<method>: Outlook integration not yet implemented"`.
- Class body MUST import cleanly with no `msal` dependency at module level
  (add a `try/except ImportError` guard around any future `import msal`).
- Add a module-level docstring explaining the stub status and Graph API endpoint
  targets (`GET /v1.0/me/messages`, `POST /v1.0/me/messages/{id}/createReply`).

**Acceptance criteria:**
- `from app.core.email.outlook import MSGraphProvider` works with no MSAL
  installed.
- `MSGraphProvider(account, session).fetch_messages()` raises `NotImplementedError`
  (not `ImportError`).

---

### Task 1.3 — Implement `ImapSmtpProvider` (core fetch path)

**File:** `backend/app/core/email/imap_smtp.py` (new file)

Implement `ImapSmtpProvider(BaseEmailProvider)`:

- Constructor: `__init__(self, account: ConnectedAccount)` — no session needed
  (credentials are fully on the account object).
- Lazy import guard for `aioimaplib` and `aiosmtplib` — raise `RuntimeError`
  with install instructions if missing.
- **`get_message(message_id: str) -> NormalizedEmail`**
  - `message_id` is a string UID.
  - Open IMAP SSL connection to `account.imap_host:account.imap_port`.
  - `FETCH {uid} (RFC822)` → parse with `email.message_from_bytes`.
  - Extract plain text (prefer `text/plain`; strip HTML as fallback).
  - Map to `NormalizedEmail(provider_type="imap_smtp", ...)`.
  - Close connection.
- **`fetch_messages(history_id, *, max_results, query) -> tuple[list[NormalizedEmail], str|None]`**
  - `history_id` is treated as the last seen UID string.
  - `SELECT INBOX`, `SEARCH UID {last_uid+1}:*` (or `SEARCH UNSEEN` on first run).
  - Fetch each UID via `get_message`; return `(messages, str(max_uid))`.
- **`create_draft(to, subject, body, *, thread_id, in_reply_to) -> str`**
  - Build MIME `EmailMessage`; `APPEND "Drafts" (\Draft) {RFC822}`.
  - Return the UID of the appended message as draft ID.
- **`send_email(to, subject, body, *, thread_id) -> str`**
  - Build MIME `EmailMessage`; connect via `aiosmtplib.SMTP` to
    `account.smtp_host:account.smtp_port` with STARTTLS.
  - Return the `Message-ID` header of the sent message.
- **`send_draft(draft_id: str) -> str`**
  - Fetch draft from Drafts via `get_message(draft_id)`.
  - Send via `send_email`; mark original UID `\Deleted` in Drafts; `EXPUNGE`.
  - Return sent message ID.
- Map all `aioimaplib`/`aiosmtplib` exceptions to `EmailProviderError`.
- Map missing/invalid credentials to `EmailProviderNotConnectedError`.

**Acceptance criteria:**
- All five methods are implemented (no `NotImplementedError`).
- `fetch_messages(history_id=None)` on a mock IMAP server returns
  `NormalizedEmail` objects with `provider_type="imap_smtp"`.
- `send_email` connects via STARTTLS (not plain-text).
- No credentials appear in log output (use `account.imap_host` in logs,
  never `account.imap_password_enc` or its decrypted value).

---

### Task 1.4 — Implement provider factory

**File:** `backend/app/core/email/factory.py` (new file)

- Implement `get_email_provider(account, session, http_client=None) -> BaseEmailProvider`
  exactly as specified in `design.md §3.5`.
- `_PROVIDER_MAP` dict maps string → class; `ImapSmtpProvider` is constructed
  with only `account` (no session/http_client — handle via a wrapper or
  `**kwargs` that each provider's `__init__` absorbs via `**_` if unused).
- `ValueError` on unknown `provider_type`.
- Re-export from `app/core/email/__init__.py`.

**Acceptance criteria:**
- `get_email_provider(ConnectedAccount(provider_type="gmail"), session)` returns
  a `GmailProvider` instance.
- `get_email_provider(ConnectedAccount(provider_type="outlook"), session)` returns
  an `MSGraphProvider` instance.
- `get_email_provider(ConnectedAccount(provider_type="imap_smtp"), session)` returns
  an `ImapSmtpProvider` instance.
- `get_email_provider(ConnectedAccount(provider_type="fax"), session)` raises
  `ValueError`.

---

### Task 1.5 — Refactor `WorkflowService` to use `BaseEmailProvider`

**File:** `backend/app/services/workflow_service.py` (modify)

Changes:

1. **Constructor** — add `email_provider: BaseEmailProvider | None = None` parameter.
   Remove `gmail_client: httpx.AsyncClient | None = None` parameter (breaking
   change — update all call sites and tests).
   Add `_provider(account) -> BaseEmailProvider` lazy-resolve helper.

2. **`pull_messages(user, account, *, max_results, query)`** — new method replacing
   `pull_gmail`. Accepts `ConnectedAccount` instead of bare `User`. Calls
   `provider.fetch_messages(...)`, persists new cursor via
   `ConnectedAccountRepository.update_history_id`, deduplicates, calls
   `run_message` per `NormalizedEmail`. Returns `{"created", "skipped", "failed", "scanned"}`.

3. **`run_message(user, account, message: NormalizedEmail)`** — replaces `run_gmail`.
   Reads `message.subject`, `message.body_text`, `message.is_noise` directly
   (no dict access). Writes `provider_message_id`, `provider_thread_id`,
   `message_id_header` to `DraftReviewRepository.create`.

4. **`approve(user, account, review)`** — replaces `self.gmail.create_draft` call
   with `provider.create_draft(...)`. Stores result in `review.provider_draft_id`.

5. **`send(user, account, review)`** — replaces `self.gmail.send_draft` call with
   `provider.send_draft(review.provider_draft_id)`.

6. **`pull_gmail` shim** — keep as a deprecated alias that resolves the user's
   `ConnectedAccount` and calls `pull_messages`. Log a deprecation warning.

7. **`run_gmail` shim** — keep as a deprecated alias that fetches the message via
   `GmailProvider.get_message` and calls `run_message`. Log a deprecation warning.

8. Remove `from app.services.gmail_service import GmailService` import.
   Remove `self.gmail` attribute.

**Acceptance criteria:**
- All existing `WorkflowService` unit tests pass (shims preserve behaviour).
- No `GmailService`, `GmailNotConnectedError`, or `GmailApiError` import
  remains in `workflow_service.py`.
- `approve` and `send` work end-to-end with a `FakeEmailProvider` injected
  via the constructor.
- `pull_gmail` shim returns the same summary dict shape as before.

---

### Task 1.6 — Update `DraftReview` model for provider-agnostic columns

**File:** `backend/app/models/draft_review.py` (modify)
**File:** `backend/app/repositories/draft_review.py` (modify)

- Rename `Mapped` attributes:
  - `gmail_message_id` → `provider_message_id`
  - `gmail_thread_id`  → `provider_thread_id`
  - `gmail_draft_id`   → `provider_draft_id`
- Add SQLAlchemy `synonym` properties for the old names so existing code
  accessing `.gmail_message_id` etc. continues to work during the transition:
  ```python
  gmail_message_id = synonym("provider_message_id")
  ```
- Update `__table_args__` `UniqueConstraint` to reference `provider_message_id`.
- In `DraftReviewRepository.create`, rename the keyword arguments to match
  the new column names (`provider_message_id=`, `provider_thread_id=`).
- Update `DraftReviewRepository.existing_message_ids` query column reference.

**Acceptance criteria:**
- `review.gmail_message_id` and `review.provider_message_id` return the same
  value (synonym works).
- All existing tests that reference `.gmail_message_id` still pass without
  modification.
- `DraftReviewRepository.create(provider_message_id="abc123")` inserts correctly.

---

### Task 1.7 — Update Celery tasks for multi-provider fan-out

**File:** `backend/app/tasks/workflow_tasks.py` (modify)

1. **`_pull_messages_async(user_id, account_id, ...)`** — new internal coroutine
   replacing `_pull_gmail_async`. Accepts `account_id` (UUID str), resolves
   `ConnectedAccount` via `ConnectedAccountRepository`, calls
   `WorkflowService.pull_messages(user, account, ...)`.

2. **`pull_messages_task`** — new Celery task with name `"workflow.pull_messages"`.
   Same retry logic as `pull_gmail_task`. `_RETRYABLE_ERRORS` extended with
   `EmailProviderError`.

3. **`pull_gmail_task`** — keep registered under `"workflow.pull_gmail"` as a
   backwards-compatible alias that resolves the account from `user_id` and
   calls `pull_messages_task`. Add deprecation log.

4. **`_list_connected_user_ids_async`** — replace `GoogleCredentialRepository`
   query with `ConnectedAccountRepository.list_connected_user_ids()`.

5. **`pull_all_connected_task`** — update fan-out to iterate `ConnectedAccount`
   rows, pass both `user_id` and `account_id` to `pull_messages_task.delay`.

**Acceptance criteria:**
- `pull_gmail_task.delay(user_id)` still dispatches work without error
  (alias works).
- `pull_all_connected_task` fans out one task per `ConnectedAccount` row,
  not per `GoogleCredential` row.
- `EmailProviderError` triggers a retry; `EmailProviderNotConnectedError`
  does not.

---

## Phase 2 — API Layer

> **Dependency:** Phase 1 must be complete and deployed.

---

### Task 2.1 — Add provider-agnostic `/email/*` routes

**File:** `backend/app/api/email/__init__.py` (new file)
**File:** `backend/app/api/router.py` (modify — add email router)

Implement three endpoints on a new `APIRouter(prefix="/email", tags=["email"])`:

**`GET /email/connection`**
- Dependency: `current_user` (existing `get_current_user` dep).
- Query `ConnectedAccountRepository.get_by_user_id(user.id)`.
- Return `{ provider_type, provider_email, connected: bool, history_id }`.
- Return `{ connected: false }` if no account exists (200, not 404).

**`GET /email/messages`**
- Query param: `max_results: int = Query(default=25, le=100)`.
- Resolve `ConnectedAccount`, call `get_email_provider(account, session)`.
- Call `provider.fetch_messages(history_id=account.history_id, max_results=max_results)`.
- Persist new cursor via `ConnectedAccountRepository.update_history_id`.
- Return the list of `NormalizedEmail` objects serialised to JSON.
- Raise `404` if no account connected.

**`POST /email/drafts`**
- Request body: `{ to: str, subject: str, body: str, thread_id?: str }`.
- Resolve account + provider; call `provider.create_draft(...)`.
- Return `{ draft_id: str }`.
- Raise `404` if no account connected.

Register the new router in `app/api/router.py` under `/api/v1/email`.

**Acceptance criteria:**
- `GET /api/v1/email/connection` returns `connected: false` for a user with
  no account.
- `GET /api/v1/email/messages` returns a list (may be empty) without error.
- All three endpoints require authentication (401 on missing JWT).
- Existing `/api/v1/gmail/*` routes still work unchanged.

---

### Task 2.2 — Add `POST /auth/imap/connect` endpoint

**File:** `backend/app/api/auth/routes.py` (modify)

Add a new route `POST /auth/imap/connect`:

- Request body schema (new Pydantic model `ImapConnectRequest` in
  `app/schemas/connected_account.py`):
  ```
  imap_host: str
  imap_port: int = 993
  smtp_host: str
  smtp_port: int = 587
  username: str
  password: str  (plaintext — encrypted before storage)
  ```
- Validation:
  - `imap_port` and `smtp_port` must be in `{993, 143, 587, 465, 25}`.
  - `imap_host` and `smtp_host` must pass a basic hostname/IP regex (no
    path components, no protocol prefix).
- Logic:
  1. `crypto.encrypt(request.password)` → `imap_password_enc`.
  2. Upsert a `ConnectedAccount(provider_type="imap_smtp", ...)` via
     `ConnectedAccountRepository.create` (or update if one exists for user).
  3. Return `201 { connected: true, provider_email: request.username }`.
- `password` MUST NOT appear in any log line.

**Acceptance criteria:**
- Port outside allowlist returns `422` with a clear error message.
- Hostname with `http://` prefix returns `422`.
- Successful connect returns `201` and `ConnectedAccountRepository` has one row.
- `crypto.decrypt(account.imap_password_enc)` equals the original password.

---

### Task 2.3 — Update `approve` and `send` API routes

**File:** `backend/app/api/reviews/__init__.py` (modify)

- The `POST /reviews/{id}/approve` and `POST /reviews/{id}/send` route
  handlers currently call `WorkflowService.approve(user, review)` and
  `WorkflowService.send(user, review)`.
- Update call sites to resolve `ConnectedAccount` and pass it:
  ```python
  account = await ConnectedAccountRepository(session).get_by_user_id(user.id)
  if account is None:
      raise HTTPException(404, "No email account connected")
  result = await svc.approve(user, account, review)
  ```
- Same pattern for `send`.

**Acceptance criteria:**
- `POST /reviews/{id}/approve` returns `200` with a `GmailProvider`-backed
  service (integration test).
- Returns `404` when no `ConnectedAccount` exists.
- No `GmailService` import remains in `reviews/__init__.py`.

---

## Phase 3 — Config & Dependency Updates

> Can run in parallel with Phase 2.

---

### Task 3.1 — Add multi-provider settings to `app/core/config.py`

**File:** `backend/app/core/config.py` (modify)

Add the following optional fields to the `Settings` class (after the Google
OAuth block):

```python
# --- Microsoft Graph / Outlook ---
outlook_client_id: str = ""
outlook_client_secret: SecretStr = SecretStr("")
outlook_tenant_id: str = "common"
outlook_redirect_uri: str = ""

# --- IMAP/SMTP defaults ---
imap_default_port: int = 993
smtp_default_port: int = 587
```

Add computed fields:

```python
@computed_field
@property
def outlook_configured(self) -> bool:
    return bool(self.outlook_client_id and self.outlook_client_secret.get_secret_value())

@computed_field
@property
def imap_smtp_configured(self) -> bool:
    # True if the app is ready to accept IMAP connections (no server-side
    # config needed beyond what the user provides at connect time).
    return True
```

**Acceptance criteria:**
- `Settings()` with no env vars set has `outlook_configured = False`.
- `Settings(outlook_client_id="x", outlook_client_secret="y")` has
  `outlook_configured = True`.
- The existing production-safety validator (`_validate_production_secrets`)
  does not flag Outlook secrets as required.

---

### Task 3.2 — Add `aioimaplib` and `aiosmtplib` to dependencies

**File:** `backend/requirements.txt` (modify)

Add pinned versions:
```
aioimaplib>=1.1.0,<2
aiosmtplib>=3.0.0,<4
```

Do NOT add `msal` in this task (deferred to Phase 4 when the Outlook OAuth
flow is implemented).

**Acceptance criteria:**
- `pip install -r requirements.txt` completes without conflicts in the
  existing virtual environment.
- `import aioimaplib` and `import aiosmtplib` succeed after install.

---

## Phase 4 — MSGraphProvider Full Implementation

> **Dependency:** Phases 0–3 complete. Requires Outlook app registration in
> Azure Entra ID and `OUTLOOK_CLIENT_ID` / `OUTLOOK_CLIENT_SECRET` configured.

---

### Task 4.1 — Implement Outlook OAuth callback flow

**File:** `backend/app/services/outlook_oauth.py` (new file)
**File:** `backend/app/api/auth/routes.py` (modify)

- Add `GET /auth/outlook/login` — redirect to
  `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize` with
  `client_id`, `scope=Mail.Read Mail.ReadWrite Mail.Send offline_access`,
  `response_type=code`.
- Add `GET /auth/outlook/callback` — exchange code for tokens via
  `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`.
- Store tokens in `ConnectedAccount(provider_type="outlook", ...)`.
- Encrypt access and refresh tokens with `crypto.encrypt` (same key as Gmail).

**Acceptance criteria:**
- Visiting `/auth/outlook/login` (unauthenticated) redirects to Microsoft.
- A valid callback code creates a `ConnectedAccount` row with
  `provider_type="outlook"`.
- Only available when `settings.outlook_configured` is True (raise `503`
  otherwise).

---

### Task 4.2 — Implement `MSGraphProvider` methods fully

**File:** `backend/app/core/email/outlook.py` (modify — replace stubs)

Replace all `NotImplementedError` bodies with real implementations:

- **`fetch_messages`** — `GET /v1.0/me/messages?$top=N&$orderby=receivedDateTime desc`
  with optional `$deltaToken` (stored as `history_id`). Map Graph message
  schema to `NormalizedEmail`. Return `(messages, next_delta_link)`.
- **`get_message`** — `GET /v1.0/me/messages/{id}`.
- **`create_draft`** — `POST /v1.0/me/messages/{id}/createReply` (Graph draft).
  Return the draft message ID.
- **`send_draft`** — `POST /v1.0/me/messages/{draft_id}/send`. Returns sent ID.
- **`send_email`** — `POST /v1.0/me/sendMail`.
- Handle 401 with a single token-refresh retry (same pattern as GmailProvider).
- Map `httpx.HTTPStatusError(401)` → `EmailProviderNotConnectedError`.
- Map all other HTTP errors → `EmailProviderError(status_code=...)`.

Add `msal` to `requirements.txt` in this task.

**Acceptance criteria:**
- `fetch_messages` returns a list of `NormalizedEmail` with
  `provider_type="outlook"` against a live Outlook sandbox or a
  `httpx.MockTransport`.
- Token expiry refreshes silently without the caller retrying.

---

## Phase 5 — Cleanup (deferred, post-stabilisation)

> Execute only after Phase 1–4 have been running in production for at least
> one full release cycle with no regressions.

---

### Task 5.1 — Remove `GmailService` and deprecation shims

**Files to modify/delete:**
- `backend/app/services/gmail_service.py` — delete file.
- `backend/app/services/workflow_service.py` — remove `pull_gmail` and
  `run_gmail` shim methods; remove `pull_gmail` Celery alias.
- `backend/app/tasks/workflow_tasks.py` — remove `pull_gmail_task` alias.
- `backend/app/api/gmail/__init__.py` — rewrite to delegate to
  `/email/*` internally, or delete and update router.
- Any remaining `from app.services.gmail_service import ...` imports.

**Acceptance criteria:**
- `grep -r "GmailService" backend/app` returns zero results.
- `grep -r "pull_gmail" backend/app` returns zero results (except git history).
- All tests pass.

---

### Task 5.2 — Write Alembic migration `0014_drop_google_credentials`

**File:** `backend/alembic/versions/0014_drop_google_credentials.py` (new file)

**upgrade:**
1. Assert (via a SELECT COUNT) that `connected_accounts` has at least as many
   Gmail rows as `google_credentials` — abort if not (safety check).
2. `DROP TABLE google_credentials`.

**downgrade:**
1. Recreate `google_credentials` table with original schema.
2. Insert rows back from `connected_accounts WHERE provider_type = 'gmail'`.

**Acceptance criteria:**
- `alembic upgrade head` removes `google_credentials` table.
- `alembic downgrade -1` recreates it with all data intact.
- Upgrade aborts with a clear error if `connected_accounts` has fewer Gmail
  rows than `google_credentials` (data-integrity guard).

---

### Task 5.3 — Remove legacy `DraftReview` column synonyms

**File:** `backend/app/models/draft_review.py` (modify)

- Remove `gmail_message_id`, `gmail_thread_id`, `gmail_draft_id` `synonym`
  properties now that all call sites use `provider_*` names.

**Acceptance criteria:**
- `review.gmail_message_id` raises `AttributeError`.
- `review.provider_message_id` works correctly.
- All tests updated to use `provider_*` attribute names.

---

## Cross-Phase: Testing Tasks

These tasks can be done alongside each phase.

---

### Task T.1 — `FakeEmailProvider` test utility

**File:** `backend/tests/fakes/email_provider.py` (new file)

Implement `FakeEmailProvider(BaseEmailProvider)` for use in all unit and
integration tests:

```python
class FakeEmailProvider(BaseEmailProvider):
    def __init__(self, messages: list[NormalizedEmail] | None = None):
        self.messages = messages or []
        self.created_drafts: list[dict] = []
        self.sent_drafts: list[str] = []
        self.sent_emails: list[dict] = []
        self.cursor = "fake-cursor-001"

    async def fetch_messages(self, history_id=None, *, max_results=25, query=None):
        return self.messages[:max_results], self.cursor

    async def get_message(self, message_id: str) -> NormalizedEmail:
        for m in self.messages:
            if m.external_message_id == message_id:
                return m
        raise EmailProviderError(f"Message {message_id} not found", status_code=404)

    async def create_draft(self, to, subject, body, *, thread_id=None, in_reply_to=None):
        draft_id = f"fake-draft-{len(self.created_drafts) + 1}"
        self.created_drafts.append({"id": draft_id, "to": to, "subject": subject})
        return draft_id

    async def send_draft(self, draft_id: str) -> str:
        self.sent_drafts.append(draft_id)
        return f"fake-sent-{draft_id}"

    async def send_email(self, to, subject, body, *, thread_id=None) -> str:
        msg_id = f"fake-msg-{len(self.sent_emails) + 1}"
        self.sent_emails.append({"id": msg_id, "to": to})
        return msg_id
```

**Acceptance criteria:**
- `FakeEmailProvider` satisfies all abstract method contracts.
- Used as the injected provider in all `WorkflowService` unit tests.

---

### Task T.2 — Unit tests for `GmailProvider`

**File:** `backend/tests/unit/email/test_gmail_provider.py` (new file)

Migrate existing `GmailService` tests to use `GmailProvider` + `ConnectedAccount`:

- `test_get_message_returns_normalized_email` — mock httpx, assert fields.
- `test_get_message_noise_label_returns_is_noise_true`.
- `test_fetch_messages_incremental_path` — mock history endpoint, assert cursor returned.
- `test_fetch_messages_fallback_path` — expired history, falls back to full list.
- `test_create_draft_returns_draft_id_string`.
- `test_send_draft_returns_message_id_string`.
- `test_token_refresh_on_401` — first call 401, second succeeds.
- `test_raises_not_connected_when_no_credential`.

---

### Task T.3 — Unit tests for `ImapSmtpProvider`

**File:** `backend/tests/unit/email/test_imap_smtp_provider.py` (new file)

Use `aioimaplib`'s `IMAPClient` mock or a local `asyncio` stream mock:

- `test_fetch_messages_returns_normalized_email`.
- `test_create_draft_appends_to_drafts_folder`.
- `test_send_email_uses_starttls`.
- `test_raises_not_connected_on_auth_failure`.

---

### Task T.4 — Unit tests for the factory

**File:** `backend/tests/unit/email/test_factory.py` (new file)

- `test_gmail_provider_returned_for_gmail`.
- `test_msgraph_provider_returned_for_outlook`.
- `test_imap_smtp_provider_returned_for_imap_smtp`.
- `test_value_error_on_unknown_provider`.

---

### Task T.5 — Integration tests for `WorkflowService` with `FakeEmailProvider`

**File:** `backend/tests/integration/test_workflow_service.py` (modify)

Replace all `GmailService` httpx mock setups with `FakeEmailProvider`:

- `test_pull_messages_creates_review_for_new_message`.
- `test_pull_messages_skips_noise_messages`.
- `test_pull_messages_skips_already_seen_messages`.
- `test_approve_calls_create_draft_on_provider`.
- `test_send_calls_send_draft_on_provider`.
- `test_pull_messages_counts_failures_without_aborting`.

---

### Task T.6 — Migration smoke test

**File:** `backend/tests/migrations/test_0013_connected_accounts.py` (new file)

Using a throwaway in-memory-compatible test DB:

- Seed one `google_credentials` row (simulate existing Gmail user).
- Run `alembic upgrade 0013`.
- Assert `connected_accounts` has one row with `provider_type="gmail"` and
  identical ciphertext values.
- Assert `draft_reviews` columns are renamed (`provider_message_id` exists,
  `gmail_message_id` does not).
- Run `alembic downgrade 0012`.
- Assert `draft_reviews` columns are back to original names.

---

## Summary: Dependency Graph

```
Phase 0 ──────────────────────────────────────────────────────────────┐
  0.1 NormalizedEmail schema                                           │
  0.2 BaseEmailProvider ABC          ← depends on 0.1                 │
  0.3 ConnectedAccount model                                           │
  0.4 ConnectedAccountRepository     ← depends on 0.3                 │
  0.5 Alembic migration 0013         ← depends on 0.3                 │
                                                                       │
Phase 1 ── depends on all Phase 0 ────────────────────────────────────┤
  1.1 GmailProvider                  ← depends on 0.1, 0.2, 0.3, 0.4 │
  1.2 MSGraphProvider stub           ← depends on 0.1, 0.2            │
  1.3 ImapSmtpProvider               ← depends on 0.1, 0.2, 0.3      │
  1.4 Factory                        ← depends on 1.1, 1.2, 1.3      │
  1.5 WorkflowService refactor       ← depends on 1.4, 0.4           │
  1.6 DraftReview model aliases      ← depends on 0.5                 │
  1.7 Celery tasks                   ← depends on 1.5, 0.4           │
                                                                       │
Phase 2 ── depends on Phase 1 ────────────────────────────────────────┤
  2.1 /email/* routes                ← depends on 1.4, 0.4           │
  2.2 POST /auth/imap/connect        ← depends on 0.3, 0.4           │
  2.3 approve/send route updates     ← depends on 1.5                 │
                                                                       │
Phase 3 ── parallel with Phase 2 ─────────────────────────────────────┤
  3.1 Config settings                                                  │
  3.2 requirements.txt additions                                       │
                                                                       │
Phase 4 ── depends on Phases 1–3 ─────────────────────────────────────┤
  4.1 Outlook OAuth flow             ← depends on 3.1                 │
  4.2 MSGraphProvider full impl      ← depends on 4.1, 1.2           │
                                                                       │
Phase 5 ── after production stabilisation ────────────────────────────┘
  5.1 Remove GmailService
  5.2 Migration 0014 drop google_credentials
  5.3 Remove synonym properties

Cross-phase tests (T.1–T.6) should be written alongside each phase.
```
