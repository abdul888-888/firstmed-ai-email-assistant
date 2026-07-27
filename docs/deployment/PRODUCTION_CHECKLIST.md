# Production Deployment Checklist

**Last Updated**: 2026-07-27  
**Status**: Ready for Production  

---

## 1. Environment & Secrets Audit

### 1.1 Required Production Environment Variables

All the following MUST be set before deployment. Empty values will cause startup failure.

| Variable | Type | Validation | Purpose |
|----------|------|-----------|---------|
| `SECRET_KEY` | `SecretStr` | Must NOT be `change-me-in-production` or other defaults. Must be 32+ random bytes (hex or base64). | JWT signing for FastAPI session tokens |
| `TOKEN_ENCRYPTION_KEY` | `SecretStr` | Must be set explicitly (no dev-derived fallback). 44-character Fernet key (base64url). Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` | Encrypts stored OAuth refresh tokens in DB |
| `PHI_ENCRYPTION_KEY` | `SecretStr` | Must be set explicitly (no dev-derived fallback). Same format as TOKEN_ENCRYPTION_KEY. Separate key for rotation independence. | Encrypts patient-identifying data in `draft_reviews` table (subject, draft_body, summary, specialist_input) |
| `POSTGRES_PASSWORD` | `SecretStr` | Must NOT be default values: `""`, `firstmed`, `changeme`, `password`, `postgres` | Database authentication for production DB cluster |
| `ANTHROPIC_API_KEY` | `SecretStr` | Set only if LLM draft generation is enabled. Empty is valid (feature disabled). | Claude API for email draft composition |
| `ANTHROPIC_BAA_SIGNED` | `bool` | MUST be `true` if `ANTHROPIC_API_KEY` is set. Startup fails otherwise. | Acknowledgment that BAA/DPA with Anthropic is signed (required for HIPAA) |
| `GOOGLE_CLIENT_ID` | `str` | Must be set (no validation format). | Google OAuth 2.0 client identifier |
| `GOOGLE_CLIENT_SECRET` | `SecretStr` | Must be set. | Google OAuth 2.0 client secret |
| `NOTION_API_KEY` | `SecretStr` | Must be set. | Notion integration token for KB sync |
| `NOTION_ROOT_PAGE_ID` | `str` | Must be set (Notion page UUID). | Root of the clinic's Notion KB structure |
| `REDIS_URL` (i.e., `CELERY_BROKER_URL`) | `str` | Format: `redis://[user:password@]host:port/db`. Default: `redis://localhost:6379/1` | Message broker for Celery async tasks |
| `CELERY_RESULT_BACKEND` | `str` | Format: `redis://[user:password@]host:port/db`. Default: `redis://localhost:6379/2` | Result backend for task status polling |
| `DATABASE_URL` | `str` | Format: `postgresql://user:password@host:port/dbname` (PostgreSQL recommended for production, SQLite unsupported in prod). | Primary application database |
| `ENVIRONMENT` | `str` | MUST be `production` | Triggers strict secret validation at startup |

### 1.2 Startup Validation (Automatic)

The app performs automatic validation via `config.py` `_validate_production_secrets()` when `ENVIRONMENT=production`:

```python
@model_validator(mode="after")
def _validate_production_secrets(self) -> Settings:
    """Fail fast on insecure/placeholder secrets when running in production."""
    if self.environment != "production":
        return self
    
    # Enforced checks:
    # 1. SECRET_KEY not in _INSECURE_SECRET_KEYS
    # 2. TOKEN_ENCRYPTION_KEY must be set (no empty string)
    # 3. PHI_ENCRYPTION_KEY must be set (no empty string)
    # 4. POSTGRES_PASSWORD not in _INSECURE_DB_PASSWORDS
    # 5. If ANTHROPIC_API_KEY is set, ANTHROPIC_BAA_SIGNED must be true
    
    if problems:
        raise ValueError("Insecure configuration for environment=production: ...")
```

**Result**: If any check fails, the application exits immediately on startup with a clear error message.

### 1.3 Dev Fallbacks (Strictly Disabled in Production)

The following dev-only fallbacks are **only active** when `ENVIRONMENT != "production"`:

- **Token Encryption**: If `TOKEN_ENCRYPTION_KEY` is empty, a deterministic key is derived from `SECRET_KEY` via `_derive_key_from_secret(secret, purpose="")`. In production, this is forbidden.
- **PHI Encryption**: If `PHI_ENCRYPTION_KEY` is empty, a deterministic key is derived from `SECRET_KEY` via `_derive_key_from_secret(secret, purpose="phi")`. In production, this is forbidden.

**Why**: Dev fallbacks ensure the app works without env-var setup during development. Production must use explicit, externally-managed keys for audit compliance and safe key rotation.

---

## 2. Database & Background Services

### 2.1 Pre-Deployment Database Checklist

#### 2.1.1 PostgreSQL Setup (Required for Production)

```bash
# 1. Create application database and user
createdb firstmed_prod
createuser firstmed_user
# Grant permissions
psql -c "ALTER USER firstmed_user WITH PASSWORD 'STRONG_PASSWORD_HERE';"
psql -c "GRANT ALL PRIVILEGES ON DATABASE firstmed_prod TO firstmed_user;"

# 2. Set DATABASE_URL environment variable
export DATABASE_URL="postgresql://firstmed_user:STRONG_PASSWORD@prod-db.example.com:5432/firstmed_prod"

# 3. Verify connection
psql $DATABASE_URL -c "SELECT 1;"  # Should return 1
```

#### 2.1.2 Run Alembic Migrations

```bash
# From backend/ directory
cd backend
alembic upgrade head
```

**Migrations included** (in order):
1. `0001_initial.py` — Base schema (users, google_credentials, documents)
2. `0002_google_credentials.py` — OAuth token storage
3. `0003_documents.py` — KB document index
4. `0004_draft_reviews.py` — Review queue (with encrypted columns)
5. `0005_review_actions.py` — Approve/reject audit trail
6. `0006_document_embeddings.py` — Embedding vectors for semantic search
7. `0007_templates.py` — Approved canned-response templates
8. `0008_pgvector_embeddings.py` — PostgreSQL pgvector extension
9. `0009_collaboration.py` — Specialist review collaboration
10. `0010_unique_gmail_message.py` — Uniqueness constraint on Gmail message IDs
11. `0011_specialist_input.py` — Specialist input on reviews
12. `0012_gmail_history_id.py` — Gmail incremental sync (historyId)

#### 2.1.3 Backfill Scripts (Run After Migrations)

**PHI Encryption Backfill** (if upgrading from pre-encrypted state):

```bash
python scripts/backfill_phi_encryption.py
```

- Idempotent: safe to re-run without data loss
- Decrypt-test-first pattern: verifies existing state before migrating
- Works on any `DraftReview` rows in the database
- Expected: ~0-50ms per row depending on DB latency

**Output** should confirm:
```
Processed X rows: Y encrypted, Z already encrypted (skipped)
```

### 2.2 Redis Setup (Required for Celery)

Celery requires a message broker and result backend. Redis is the recommended choice.

#### 2.2.1 Redis Installation & Configuration

```bash
# Option A: Docker (recommended for cloud)
docker run -d \
  --name redis-celery-broker \
  -p 6379:6379 \
  redis:7-alpine \
  redis-server --appendonly yes

# Option B: systemd (Linux VMs)
sudo apt-get install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Verify connection
redis-cli ping  # Should return PONG
```

#### 2.2.2 Configure Environment Variables

```bash
# Default (localhost, development only)
export CELERY_BROKER_URL="redis://localhost:6379/1"
export CELERY_RESULT_BACKEND="redis://localhost:6379/2"

# Production (cloud Redis, with authentication)
export CELERY_BROKER_URL="redis://:PASSWORD@redis-prod.example.com:6379/1"
export CELERY_RESULT_BACKEND="redis://:PASSWORD@redis-prod.example.com:6379/2"
```

**Note**: Use separate DB numbers (1 and 2) to avoid key collisions.

#### 2.2.3 Production Redis Checklist

- [ ] Redis configured with `appendonly yes` (AOF persistence)
- [ ] Backups enabled (daily snapshots)
- [ ] Memory limit set (e.g., `maxmemory 2gb` for moderate load)
- [ ] Eviction policy: `maxmemory-policy allkeys-lru` (evict oldest on memory pressure)
- [ ] Port 6379 (or custom port) open only to application servers
- [ ] TLS/SSL encryption in transit if Redis is remote

### 2.3 Celery Worker Startup

#### 2.3.1 Start the Main Worker

```bash
# From backend/ directory
cd backend
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

**Important flags**:
- `--concurrency=4` — Number of concurrent task workers (tune to CPU cores)
- `--max-tasks-per-child=100` — Recycle worker processes after N tasks (prevents memory leaks)
- `--pool=prefork` — Use process-based concurrency (default on Linux)
- `--pool=solo` — Use single-process mode (Windows or single-threaded testing)

**Example production command**:
```bash
celery -A app.workers.celery_app.celery_app worker \
  --loglevel=info \
  --concurrency=8 \
  --max-tasks-per-child=100 \
  --prefetch-multiplier=1
```

#### 2.3.2 Start the Beat Scheduler (Periodic Tasks)

In a **separate process** (supervisor/systemd recommended):

```bash
celery -A app.workers.celery_app.celery_app beat --loglevel=info
```

**What it does**: Periodically fans out `workflow.pull_all_connected` to pull new emails from all connected user mailboxes (interval: `GMAIL_AUTO_PULL_INTERVAL_SECONDS`, default 300 seconds / 5 minutes).

---

## 3. Final Verification Steps

### 3.1 Pre-Deployment Testing

```bash
# Run the full test suite
cd backend
pytest -v

# Expected: All 267+ tests pass (exit code 0)
```

**Test coverage**:
- `tests/unit/` — Pure logic tests (safety gates, draft generation, encryption)
- `tests/api/` — API endpoint tests (workflows, reviews, auth)
- `tests/integration/` — Database + external service integration

### 3.2 Health Check

Once the application is running (FastAPI on port 8000):

```bash
# Check API readiness
curl -s http://localhost:8000/health || echo "Health endpoint not found"

# Check docs (OpenAPI)
curl -s http://localhost:8000/docs | head -20

# Check Celery connectivity
celery -A app.workers.celery_app.celery_app inspect active
# Should connect to Redis and list active workers
```

### 3.3 Smoke Test (Manual)

1. **Sign in** with a test Google account (SSO flow via `/auth/google`)
2. **Sync Gmail** via `POST /api/v1/workflows/pull-async` (verify task queues)
3. **Check task status** via `GET /api/v1/workflows/pull-async/{task_id}` (verify polling)
4. **View draft review** via frontend dashboard (verify decryption of PHI columns)
5. **Test safety gate** by sending a test email with "chest pain" keyword (should route to physician, not draft)

---

## 4. Security Checklist (Pre-Production)

- [ ] **Secrets**: All required env vars set and validated (no defaults)
- [ ] **Database**: PostgreSQL running, migrations applied, backfill scripts run
- [ ] **Redis**: Running and accessible, persistence enabled
- [ ] **Celery**: Worker and beat processes started (separate processes)
- [ ] **TLS/HTTPS**: Frontend and API endpoints served over HTTPS (not HTTP)
- [ ] **CORS**: `BACKEND_CORS_ORIGINS` limited to trusted frontend domains (not `*`)
- [ ] **Anthropic BAA**: Signed agreement confirmed before first patient email
- [ ] **Logging**: Application logs routed to centralized log aggregator (e.g., ELK, CloudWatch)
- [ ] **Monitoring**: Celery task failure alerts configured
- [ ] **Backups**: Database and Redis snapshots scheduled (daily minimum)
- [ ] **Access Control**: Only authorized staff can access the review dashboard
- [ ] **Audit Logging**: Review approval/rejection/send actions logged (for HIPAA compliance)

---

## 5. Post-Deployment

### 5.1 Monitor for Errors

**First 24 hours**:
- [ ] Check application logs for exceptions or 5xx errors
- [ ] Verify Celery tasks are completing (check Redis result backend)
- [ ] Monitor database query latency (should be <100ms for typical queries)
- [ ] Test email notifications (if configured) for review approvals

### 5.2 Periodic Maintenance

- **Weekly**: Review and archive old task results from Redis (to prevent memory buildup)
- **Monthly**: Rotate encryption keys (if supported by key management system)
- **Quarterly**: Run backfill script to ensure no plaintext data lingers (optional if migrations are current)

---

## Deployment Runbook

### Quick Start (Development)

```bash
# 1. Set minimal env vars
export ENVIRONMENT=development
export DATABASE_URL=sqlite:///firstmed.db
export SECRET_KEY=dev-change-me-in-production

# 2. Run migrations
cd backend && alembic upgrade head

# 3. Start FastAPI
uvicorn app.main:app --reload --port 8000

# 4. In another terminal, start Celery worker
celery -A app.workers.celery_app.celery_app worker --loglevel=info

# 5. In a third terminal, start Celery beat
celery -A app.workers.celery_app.celery_app beat --loglevel=info

# 6. Start frontend (in frontend/ directory)
npm run dev
```

### Production Deployment (Docker/K8s)

See `docs/deployment/docker-compose.yml` and `docs/deployment/kubernetes/` for containerized examples.

---

## Troubleshooting

| Issue | Symptom | Solution |
|-------|---------|----------|
| **Startup fails with "Insecure configuration..."** | App exits with ValueError listing missing secrets | Check `ENVIRONMENT=production` and ensure all required env vars are set (see section 1.1) |
| **Celery tasks queue but never execute** | Tasks stuck in PENDING state | Verify Redis is running and reachable; check `CELERY_BROKER_URL` points to the correct host/port |
| **PHI columns decrypt to gibberish** | Draft reviews show corrupted text | Verify `PHI_ENCRYPTION_KEY` is consistent between app instances; re-run backfill script after key rotation |
| **Gmail sync hangs or times out** | `pull_gmail_task` never completes | Check Gmail API quota (5 requests/sec per user); verify Google credentials are valid and OAuth scopes include `gmail.readonly` |
| **Database connection refused** | PostgreSQL connection errors | Verify `DATABASE_URL` format, network connectivity to DB host, and firewall rules |

---

## Sign-Off

- [ ] Environment variables validated at startup
- [ ] Database migrations applied successfully
- [ ] Redis broker and result backend operational
- [ ] Celery worker and beat processes running
- [ ] Full test suite passing (267+ tests)
- [ ] Security checklist items completed
- [ ] Team trained on operational procedures

**Date Deployed**: _______________  
**Deployed By**: _______________  
**Approved By**: _______________
