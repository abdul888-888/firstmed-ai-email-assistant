# Staging Deployment Guide (Docker Compose)

**Status**: Production-simulated Docker environment  
**Date**: 2026-07-27  
**Components**: PostgreSQL, Redis, FastAPI, Celery Worker, Celery Beat

---

## Prerequisites

- ✅ Docker installed (version 20.10+)
- ✅ Docker Compose installed (version 2.0+)
- ✅ Git repository cloned
- ✅ Google OAuth credentials (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)

**Verify Docker**:
```bash
docker --version
docker-compose --version
```

---

## Step-by-Step Deployment

### Step 1: Configure Environment Variables

Copy and customize the staging environment file:

```bash
# Edit the .env.staging file with your credentials
cd C:\Users\HP\firstmed-ai-email-assistant
notepad .env.staging
```

**Required fields to update**:
```
GOOGLE_CLIENT_ID=your-actual-google-client-id
GOOGLE_CLIENT_SECRET=your-actual-google-client-secret
```

**Optional (for production)**:
```
SECRET_KEY=<generate-a-strong-random-key>
TOKEN_ENCRYPTION_KEY=<generate-a-fernet-key>
PHI_ENCRYPTION_KEY=<generate-a-fernet-key>
```

**To generate secure keys**:
```bash
# Secret key (32+ bytes)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Fernet keys (for encryption)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Step 2: Build Docker Images

```bash
cd C:\Users\HP\firstmed-ai-email-assistant
docker-compose -f docker-compose.staging.yml build
```

**Expected output**:
```
Building postgres
Building redis
Building api
Building celery_worker
Building celery_beat
Successfully built ...
```

**Duration**: 3-5 minutes (first build is slower)

### Step 3: Start All Services

```bash
docker-compose -f docker-compose.staging.yml up
```

**Expected output**:
```
[+] Running 5/5
 ✔ Container firstmed-postgres-staging  Started
 ✔ Container firstmed-redis-staging     Started
 ✔ Container firstmed-api-staging       Started
 ✔ Container firstmed-celery-worker-staging Started
 ✔ Container firstmed-celery-beat-staging  Started
```

**Leave this running** (all logs visible in one terminal).

---

### Step 4: Run Database Migrations

**In a new terminal** (keep the Docker containers running):

```bash
docker-compose -f docker-compose.staging.yml exec api alembic upgrade head
```

**Expected output**:
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl with dialect postgresql
INFO  [alembic.runtime.migration] Will assume transactional DDL is supported by the backend
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial
INFO  [alembic.runtime.migration] Running upgrade 0001_initial -> 0002_google_credentials
...
INFO  [alembic.runtime.migration] Running upgrade 0011_specialist_input -> 0012_gmail_history_id
```

**All 12 migrations should complete successfully.**

---

### Step 5: Seed Demo Data

```bash
docker-compose -f docker-compose.staging.yml exec api python scripts/seed_demo.py
```

**Expected output**:
```
Seeding demo Notion documents...
Seeding demo templates...
Seeding demo users...
Demo data seeded successfully!
```

---

## Verification Checks

### Check 1: Database Connection

```bash
docker-compose -f docker-compose.staging.yml exec postgres psql -U firstmed_user -d firstmed_staging -c "SELECT COUNT(*) FROM users;"
```

**Expected**: Shows a count (should be > 0 after seeding)

### Check 2: Redis Connection

```bash
docker-compose -f docker-compose.staging.yml exec redis redis-cli ping
```

**Expected**: `PONG`

### Check 3: API Health

```bash
curl http://localhost:8000/health
```

**Expected**:
```json
{"status": "ok"}
```

### Check 4: FastAPI Docs

Open browser: http://localhost:8000/docs

**Expected**: Interactive API documentation (Swagger UI)

### Check 5: Celery Worker Status

Check the Docker logs for:
```
[*] celery@... ready.
[*] Connected to redis://redis:6379/1
```

### Check 6: Database Tables

```bash
docker-compose -f docker-compose.staging.yml exec postgres psql -U firstmed_user -d firstmed_staging -c "\dt"
```

**Expected**: List of tables (users, documents, templates, draft_reviews, etc.)

---

## Live Email Test

### Setup

1. **Start the frontend** (new terminal):
   ```bash
   cd frontend
   npm run dev
   ```

2. **Open browser**: http://localhost:3000

### Test Flow

1. **Sign in** with Google (uses GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET from .env.staging)
2. **Send test email** to your Gmail inbox:
   - Subject: `Test email - MRI pricing`
   - Body: `Hi, how much does an MRI scan cost at your clinic? Thanks!`
3. **Click "Sync Gmail"** in dashboard
4. **Check Celery logs** — should see:
   ```
   [*] Task workflow.pull_gmail_task[...] received
   [*] Task workflow.pull_gmail_task[...] succeeded
   ```
5. **View Reviews dashboard** — email should appear with draft

---

## Viewing Logs

**All services**:
```bash
docker-compose -f docker-compose.staging.yml logs -f
```

**Specific service**:
```bash
docker-compose -f docker-compose.staging.yml logs -f api
docker-compose -f docker-compose.staging.yml logs -f celery_worker
docker-compose -f docker-compose.staging.yml logs -f celery_beat
```

---

## Stopping & Cleaning Up

**Stop all services** (preserves data):
```bash
docker-compose -f docker-compose.staging.yml down
```

**Stop and remove all data** (fresh start):
```bash
docker-compose -f docker-compose.staging.yml down -v
```

**Remove images** (frees disk space):
```bash
docker-compose -f docker-compose.staging.yml down --rmi all
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **Port 5432 already in use** | `docker ps` to see running containers, or use different port in docker-compose.yml |
| **Port 8000 already in use** | Same as above, or use different port |
| **"connect to server: No such file or directory"** | PostgreSQL not ready; wait 10s and retry |
| **Alembic migration fails** | Check DATABASE_URL is correct, run `docker-compose down -v` and start fresh |
| **Celery task stuck in PENDING** | Check Redis is running: `docker-compose exec redis redis-cli ping` |
| **No emails syncing** | Verify GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET are correct |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Network                           │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐ │
│  │  PostgreSQL  │  │    Redis     │  │   FastAPI (API)   │ │
│  │   :5432      │  │   :6379      │  │     :8000         │ │
│  └──────────────┘  └──────────────┘  └───────────────────┘ │
│                         ↑                    ↑               │
│                         │ (broker)           │               │
│                         │ (results)          │               │
│  ┌──────────────────────┴────────────────────┴────────────┐ │
│  │                    Celery                              │ │
│  │  ┌──────────────┐                  ┌──────────────┐   │ │
│  │  │   Worker    │                  │    Beat      │   │ │
│  │  │ (tasks)     │                  │ (scheduler)  │   │ │
│  │  └──────────────┘                  └──────────────┘   │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│                ↑                                              │
│          http :3000 (Frontend - npm run dev)                 │
│          http :8000 (API)                                    │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Deployment Checklist

- [ ] Docker & Docker Compose installed
- [ ] `.env.staging` updated with Google OAuth credentials
- [ ] `docker-compose build` completed successfully
- [ ] `docker-compose up` running (all 5 containers healthy)
- [ ] Alembic migrations ran (12 migrations)
- [ ] Demo data seeded
- [ ] API health check passes (http://localhost:8000/health)
- [ ] Redis connectivity verified (redis-cli ping returns PONG)
- [ ] Database tables created (psql \dt shows all tables)
- [ ] Frontend running (http://localhost:3000)
- [ ] Google OAuth signin works
- [ ] Test email synced successfully
- [ ] Draft generated with citations

---

## Next Steps

Once staging is verified:

1. **Production Deployment**: Replace staging services with production-grade infrastructure
2. **Client Notion Setup**: Get client's Notion API key + database ID
3. **Anthropic Setup**: Enable AI drafting with signed BAA
4. **Monitoring**: Add Prometheus/Datadog for production monitoring
5. **Backups**: Configure daily database/Redis snapshots

---

## Support

For issues, check:
- Docker logs: `docker-compose logs -f`
- Database logs: `docker-compose logs -f postgres`
- API logs: `docker-compose logs -f api`
- Celery logs: `docker-compose logs -f celery_worker`
