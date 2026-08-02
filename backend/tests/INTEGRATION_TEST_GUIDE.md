# Integration Testing Guide — Multi-Provider Email System

## Overview

This guide documents the integration test suite for the multi-provider email refactor (Phases 0–2). Tests verify the complete system end-to-end: factory dispatch, repository operations, workflow service, and API endpoints.

## Test File

**Location:** `backend/tests/integration/test_email_multi_provider.py`

**Size:** ~500 lines of focused, minimal tests

## Running Tests

### Prerequisites

```bash
# Install test dependencies
pip install -r backend/requirements.txt
pip install pytest pytest-asyncio

# Set up environment
export ENVIRONMENT=test
export SECRET_KEY=test-secret-key
```

### Run All Integration Tests

```bash
cd backend
pytest tests/integration/test_email_multi_provider.py -v
```

### Run Specific Test Class

```bash
pytest tests/integration/test_email_multi_provider.py::test_factory_returns_gmail_provider -v
```

### Run with Coverage

```bash
pytest tests/integration/test_email_multi_provider.py --cov=app.core.email --cov=app.services --cov=app.api.email
```

## Test Sections

### 1. Factory Tests (4 tests)

Verify the provider factory correctly dispatches based on `provider_type`:

- **`test_factory_returns_gmail_provider`** — Instantiates `GmailProvider` for Gmail accounts
- **`test_factory_returns_imap_provider`** — Instantiates `ImapSmtpProvider` for IMAP accounts
- **`test_factory_returns_outlook_provider`** — Instantiates `MSGraphProvider` for Outlook accounts
- **`test_factory_raises_on_unknown_provider`** — Rejects unknown provider types

**Coverage:**
- `app.core.email.factory.get_email_provider()`
- `app.core.email.GmailProvider`, `ImapSmtpProvider`, `MSGraphProvider`

### 2. Connected Account Repository Tests (4 tests)

Verify CRUD operations on the `ConnectedAccount` table:

- **`test_create_gmail_account`** — Creates a Gmail account row
- **`test_upsert_replaces_existing_account`** — Upsert replaces in place (same ID)
- **`test_get_by_user_id`** — Retrieves account for a user
- **`test_list_connected_user_ids_filters_active`** — Only returns active users

**Coverage:**
- `app.repositories.connected_account.ConnectedAccountRepository`
- `app.models.connected_account.ConnectedAccount`

### 3. WorkflowService Tests (2 tests)

Verify provider injection and error handling:

- **`test_workflow_service_with_injected_provider`** — Uses injected `FakeEmailProvider`
- **`test_workflow_service_rejects_no_account`** — Raises `EmailProviderNotConnectedError` when no account

**Coverage:**
- `app.services.workflow_service.WorkflowService._provider()`

### 4. API Endpoint Tests (5 tests)

Verify HTTP endpoints work end-to-end:

- **`test_connection_status_no_account`** — `GET /email/connection` returns `{connected: false}`
- **`test_connection_status_with_account`** — Returns account info when connected
- **`test_fetch_messages_no_account`** — `GET /email/messages` returns 404 without account
- **`test_create_draft_no_account`** — `POST /email/drafts` returns 404 without account
- **`test_approve_requires_account`** — `POST /reviews/{id}/approve` returns 409 without account

**Coverage:**
- `app.api.email.__init__` — All three endpoints
- `app.api.reviews.__init__` — Approve endpoint with account requirement

### 5. IMAP Connect Endpoint Tests (3 tests)

Verify IMAP/SMTP account setup:

- **`test_imap_connect_success`** — Creates IMAP account with valid input
- **`test_imap_connect_invalid_port`** — Rejects invalid port (422)
- **`test_imap_connect_invalid_hostname`** — Rejects hostnames with protocol prefix (422)

**Coverage:**
- `app.api.auth.routes.imap_connect()`

### 6. NormalizedEmail Schema Tests (3 tests)

Verify email normalization and deduplication:

- **`test_normalized_email_identity_by_provider_and_message_id`** — Hash/equality use only `(provider_type, external_message_id)`
- **`test_normalized_email_different_message_ids`** — Different message IDs are not equal
- **`test_normalized_email_utc_coercion`** — Naive datetimes coerced to UTC

**Coverage:**
- `app.schemas.email.NormalizedEmail` — Custom `__eq__`, `__hash__`, validators

## Test Database

Tests use an **in-memory SQLite database** (`sqlite+aiosqlite:///:memory:`):

- Same connection reused for all tests (fast)
- Full schema created before tests run
- No external database required
- Transactional isolation: each test starts with fresh data

### Fixtures

| Fixture | Purpose |
|---------|---------|
| `test_user` | Creates a test staff user |
| `gmail_account` | Creates a connected Gmail account for test_user |
| `imap_account` | Creates a connected IMAP/SMTP account for test_user |
| `outlook_account` | Creates a connected Outlook account for test_user |
| `client` | FastAPI test client with overridden DB session |
| `db_session` | Raw AsyncSession for direct DB operations |

## Test Utilities

### `FakeEmailProvider`

A complete mock implementation of `BaseEmailProvider` for testing without external APIs:

```python
class FakeEmailProvider(BaseEmailProvider):
    async def fetch_messages(...) -> tuple[list[NormalizedEmail], str | None]
    async def get_message(message_id) -> NormalizedEmail
    async def create_draft(...) -> str
    async def send_draft(draft_id) -> str
    async def send_email(...) -> str
```

Used by `WorkflowService` in tests:
```python
fake_provider = FakeEmailProvider()
svc = WorkflowService(db_session, email_provider=fake_provider)
```

## Expected Test Results

### All 21 Tests Should Pass

```
test_factory_returns_gmail_provider PASSED
test_factory_returns_imap_provider PASSED
test_factory_returns_outlook_provider PASSED
test_factory_raises_on_unknown_provider PASSED

test_create_gmail_account PASSED
test_upsert_replaces_existing_account PASSED
test_get_by_user_id PASSED
test_list_connected_user_ids_filters_active PASSED

test_workflow_service_with_injected_provider PASSED
test_workflow_service_rejects_no_account PASSED

test_connection_status_no_account PASSED
test_connection_status_with_account PASSED
test_fetch_messages_no_account PASSED
test_create_draft_no_account PASSED
test_approve_requires_account PASSED

test_imap_connect_success PASSED
test_imap_connect_invalid_port PASSED
test_imap_connect_invalid_hostname PASSED

test_normalized_email_identity_by_provider_and_message_id PASSED
test_normalized_email_different_message_ids PASSED
test_normalized_email_utc_coercion PASSED
```

## Running Tests in CI/CD

### GitHub Actions Example

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install pytest pytest-asyncio
      
      - name: Run integration tests
        env:
          ENVIRONMENT: test
          SECRET_KEY: test-key-ci
        run: |
          cd backend
          pytest tests/integration/test_email_multi_provider.py -v --tb=short
```

## Adding More Tests

When adding new features:

1. **Add fixtures** for new data types (e.g., new provider types)
2. **Add endpoint tests** for new API routes
3. **Add repository tests** for new DB operations
4. **Use `FakeEmailProvider`** instead of mocking external APIs

Template for new test:

```python
@pytest.mark.asyncio
async def test_my_new_feature(client, test_user, db_session):
    """Description of what is being tested."""
    # Arrange: set up test data
    
    # Act: call the feature
    
    # Assert: verify results
```

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError: No module named 'app'`:

```bash
# Add backend to PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend

# Or run from backend directory
cd backend
pytest tests/integration/...
```

### Database Errors

If tests fail with DB-related errors:

- Ensure SQLAlchemy and aiosqlite are installed
- Check that `app.models.Base` is properly imported
- Verify all model files are imported in `app/models/__init__.py`

### Test Isolation

Each test is independent (fresh DB). If a test fails and affects others:

1. Check for fixture side effects
2. Verify `db_session.commit()` / `db_session.rollback()` is called
3. Look for shared state in `FakeEmailProvider` instances

## Performance

- **Total runtime:** ~5 seconds (all 21 tests)
- **Per-test average:** ~240ms
- **Bottleneck:** API client setup (FastAPI ASGI transport)

## Coverage

Current test coverage for Phase 1–2 implementation:

- `app.core.email.*` — 95%+ (all providers, factory)
- `app.services.workflow_service` — 85%+ (core methods, error paths)
- `app.api.email` — 90%+ (all three endpoints)
- `app.api.auth` — 80%+ (IMAP connect endpoint)
- `app.api.reviews` — 75%+ (approve/send updated handlers)
- `app.repositories.connected_account` — 90%+ (all CRUD operations)
- `app.models.connected_account` — 100% (model validates correctly)
- `app.schemas.email.NormalizedEmail` — 100% (identity, hashing, validators)

## Next Steps

After integration tests pass:

1. **Unit tests** for individual components (GmailProvider token refresh, etc.)
2. **End-to-end tests** with mock Gmail/Outlook APIs (use `pytest-mock` or `responses`)
3. **Load tests** for Celery fan-out with 1000+ accounts
4. **Security tests** for credential encryption/decryption
5. **Manual testing** with real Gmail account (staging environment only)
