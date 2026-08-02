# Multi-Provider Email Integration Test Checklist

## Pre-Test Setup

- [ ] Install pytest and pytest-asyncio
  ```bash
  pip install pytest pytest-asyncio httpx
  ```

- [ ] Set environment variables
  ```bash
  export ENVIRONMENT=test
  export SECRET_KEY=test-secret-key
  ```

- [ ] Verify all imports work
  ```bash
  python -c "from app.core.email import get_email_provider; print('✓ Imports OK')"
  ```

## Run Tests

### Full Suite
```bash
cd backend
pytest tests/integration/test_email_multi_provider.py -v
```

**Expected:** 21/21 PASSED

### By Category

**Factory Tests (4 tests):**
```bash
pytest tests/integration/test_email_multi_provider.py -k "factory" -v
```

**Repository Tests (4 tests):**
```bash
pytest tests/integration/test_email_multi_provider.py -k "account" -v
```

**WorkflowService Tests (2 tests):**
```bash
pytest tests/integration/test_email_multi_provider.py -k "workflow" -v
```

**API Tests (5 tests):**
```bash
pytest tests/integration/test_email_multi_provider.py -k "connection or fetch or create_draft or approve" -v
```

**IMAP Connect Tests (3 tests):**
```bash
pytest tests/integration/test_email_multi_provider.py -k "imap_connect" -v
```

**Schema Tests (3 tests):**
```bash
pytest tests/integration/test_email_multi_provider.py -k "normalized_email" -v
```

## Test Categories & Expected Results

### ✅ Factory Tests

| Test | Expects |
|------|---------|
| `test_factory_returns_gmail_provider` | `GmailProvider` instance |
| `test_factory_returns_imap_provider` | `ImapSmtpProvider` instance |
| `test_factory_returns_outlook_provider` | `MSGraphProvider` instance |
| `test_factory_raises_on_unknown_provider` | `ValueError` exception |

### ✅ Repository Tests

| Test | Expects |
|------|---------|
| `test_create_gmail_account` | Account with `provider_type="gmail"` |
| `test_upsert_replaces_existing_account` | Same ID, new provider type |
| `test_get_by_user_id` | Account retrieved by user |
| `test_list_connected_user_ids_filters_active` | Only active users returned |

### ✅ WorkflowService Tests

| Test | Expects |
|------|---------|
| `test_workflow_service_with_injected_provider` | Injected provider returned |
| `test_workflow_service_rejects_no_account` | `EmailProviderNotConnectedError` raised |

### ✅ API Tests

| Test | Endpoint | Expects |
|------|----------|---------|
| `test_connection_status_no_account` | `GET /email/connection` | 200, `{connected: false}` |
| `test_connection_status_with_account` | `GET /email/connection` | 200, `{connected: true, ...}` |
| `test_fetch_messages_no_account` | `GET /email/messages` | 404 |
| `test_create_draft_no_account` | `POST /email/drafts` | 404 |
| `test_approve_requires_account` | `POST /reviews/{id}/approve` | 404 |

### ✅ IMAP Connect Tests

| Test | Expects |
|------|---------|
| `test_imap_connect_success` | 201, `{connected: true, provider_email: ...}` |
| `test_imap_connect_invalid_port` | 422, "imap_port must be one of..." |
| `test_imap_connect_invalid_hostname` | 422, "valid hostnames..." |

### ✅ Schema Tests

| Test | Expects |
|------|---------|
| `test_normalized_email_identity_by_provider_and_message_id` | Same hash/equality for same ID |
| `test_normalized_email_different_message_ids` | Different hash/inequality for different IDs |
| `test_normalized_email_utc_coercion` | Naive datetime → UTC-aware |

## Verification Steps

### 1. All Imports Work
```bash
python -c "
from app.core.email import BaseEmailProvider, get_email_provider
from app.models.connected_account import ConnectedAccount
from app.repositories.connected_account import ConnectedAccountRepository
from app.services.workflow_service import WorkflowService
from app.api.email import router
from app.schemas.email import NormalizedEmail
print('✓ All imports successful')
"
```

### 2. Models Create Correctly
```bash
python -c "
from app.models.connected_account import ConnectedAccount
from app.models.draft_review import DraftReview
import datetime
# Verify model fields exist
assert hasattr(ConnectedAccount, 'provider_type')
assert hasattr(ConnectedAccount, 'history_id')
assert hasattr(DraftReview, 'provider_message_id')
assert hasattr(DraftReview, 'provider_draft_id')
print('✓ Models configured correctly')
"
```

### 3. Factory Dispatch Works
```bash
python -c "
import asyncio
from app.core.email import get_email_provider, GmailProvider, ImapSmtpProvider
from app.models.connected_account import ConnectedAccount
import uuid
from datetime import datetime, timedelta

# Test Gmail
acc = ConnectedAccount(
    user_id=uuid.uuid4(),
    provider_type='gmail',
    provider_email='test@gmail.com'
)
provider = get_email_provider(acc, None)
assert isinstance(provider, GmailProvider)

# Test IMAP
acc = ConnectedAccount(
    user_id=uuid.uuid4(),
    provider_type='imap_smtp',
    provider_email='user@example.com',
    imap_host='mail.example.com',
    imap_port=993,
    smtp_host='mail.example.com',
    smtp_port=587,
)
provider = get_email_provider(acc, None)
assert isinstance(provider, ImapSmtpProvider)

print('✓ Factory dispatch works')
"
```

### 4. API Endpoints Compile
```bash
python -c "
from app.api.email import router as email_router
from app.api.router import api_router
from app.api.auth import routes as auth_routes
# Verify routers exist and have routes
assert len(email_router.routes) > 0
assert any('email' in str(r.path) for r in api_router.routes)
print('✓ API routes compiled')
"
```

## Troubleshooting

### Test Import Fails
```bash
# Problem: ModuleNotFoundError: No module named 'app'
# Solution:
export PYTHONPATH=$(pwd)/backend:$PYTHONPATH
cd backend
pytest tests/integration/test_email_multi_provider.py -v
```

### Database Tests Fail
```bash
# Problem: "aiosqlite not found" or DB errors
# Solution:
pip install aiosqlite sqlalchemy pytest-asyncio

# Verify installation:
python -c "import aiosqlite; import sqlalchemy; print('✓ DB libs OK')"
```

### Async Tests Timeout
```bash
# Problem: Tests hang or timeout
# Solution:
pytest tests/integration/test_email_multi_provider.py --timeout=10 -v

# Or increase timeout in conftest.py:
# @pytest.mark.timeout(30)
```

### Port Validation Tests Fail
```bash
# Problem: IMAP port validation test fails
# Solution: Verify test uses allowed ports {25, 143, 465, 587, 993}
# Current test uses 993 (IMAPS) and 587 (SMTP-TLS) — both valid

# Test ports allowed:
# - 143 (IMAP plain)
# - 993 (IMAPS/SSL)
# - 25 (SMTP plain)
# - 465 (SMTPS/SSL)
# - 587 (SMTP-TLS)
```

## CI/CD Integration

### GitHub Actions
Add to `.github/workflows/test.yml`:
```yaml
- name: Integration Tests
  run: |
    cd backend
    pytest tests/integration/test_email_multi_provider.py -v --tb=short
```

### GitLab CI
Add to `.gitlab-ci.yml`:
```yaml
integration_tests:
  script:
    - cd backend
    - pytest tests/integration/test_email_multi_provider.py -v
```

## Performance Baselines

Expected test runtime:
- Total suite: ~5-10 seconds
- Per test: ~200-500ms
- Slowest: API client setup (~1s per test)

If tests take significantly longer:
1. Check for slow imports
2. Verify SQLite is in-memory (`:memory:`)
3. Profile with `pytest --durations=10`

## Success Criteria

✅ **All 21 tests pass**
✅ **No import errors**
✅ **No database connectivity errors**
✅ **All API endpoints respond correctly**
✅ **IMAP validation works**
✅ **Provider factory dispatches correctly**
✅ **WorkflowService handles missing accounts**

## Post-Test Steps

1. [ ] Run full test suite once more
2. [ ] Check for any skipped tests
3. [ ] Review any warnings
4. [ ] Verify coverage metrics (if using pytest-cov)
5. [ ] Commit and push passing tests
6. [ ] Update CI/CD if needed

## Quick Reference Commands

```bash
# Run all tests
pytest tests/integration/test_email_multi_provider.py -v

# Run tests with coverage
pytest tests/integration/test_email_multi_provider.py --cov=app.core.email --cov=app.api.email

# Run specific test
pytest tests/integration/test_email_multi_provider.py::test_factory_returns_gmail_provider -v

# Run tests matching pattern
pytest tests/integration/test_email_multi_provider.py -k "factory" -v

# Run with verbose output and full diffs
pytest tests/integration/test_email_multi_provider.py -vv -s

# Stop on first failure
pytest tests/integration/test_email_multi_provider.py -x

# Show slowest 10 tests
pytest tests/integration/test_email_multi_provider.py --durations=10
```
