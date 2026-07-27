# Railway Deployment Guide

**Platform**: Railway.app  
**Status**: Production-ready for client testing  
**Services**: FastAPI Backend + Celery Worker/Beat + PostgreSQL + Redis  

---

## Prerequisites

- ✅ GitHub account with repo pushed (https://github.com/abdul888-888/firstmed-ai-email-assistant)
- ✅ Railway.app account (free tier available: https://railway.app)
- ✅ Google OAuth Client ID & Secret
- ✅ Optional: Notion API key (for real KB, not needed for demo)
- ✅ Optional: Anthropic API key (for LLM drafting, not needed for demo)

---

## Part 1: Create Railway Project & Link GitHub

### Step 1: Create a New Railway Project

1. Go to https://railway.app
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Authorize Railway to access your GitHub account
5. Select **`abdul888-888/firstmed-ai-email-assistant`** repository
6. Click **"Deploy Now"**

**Expected**: Railway clones your repo and detects `Procfile`

---

### Step 2: Verify Service Detection

Railway should auto-detect **3 services** from the `Procfile`:
- `api` — FastAPI backend
- `worker` — Celery worker
- `beat` — Celery beat scheduler

**If services don't appear**: Manually add them (see Part 2, Step 4)

---

## Part 2: Add PostgreSQL & Redis Plugins

### Step 1: Add PostgreSQL Database

1. In Railway project dashboard, click **"+ Add Service"**
2. Select **"Database"** → **"PostgreSQL"**
3. Railway auto-generates `DATABASE_URL` environment variable
4. Confirm and create

**Result**: PostgreSQL service running, `DATABASE_URL` available

### Step 2: Add Redis Cache

1. Click **"+ Add Service"** again
2. Select **"Database"** → **"Redis"**
3. Railway auto-generates `REDIS_URL` environment variable
4. Confirm and create

**Result**: Redis service running, `REDIS_URL` available

### Step 3: Verify Database URLs

In Railway dashboard, go to each service and check environment variables:
- PostgreSQL service → should have `DATABASE_URL`
- Redis service → should have `REDIS_URL`

---

## Part 3: Configure Environment Variables

### Step 1: Get Pre-Generated Variables

Railway auto-generates:
```
DATABASE_URL=postgresql://user:password@host:port/dbname
REDIS_URL=redis://default:password@host:port
```

These are **already set** in PostgreSQL & Redis services.

### Step 2: Configure API Service Environment Variables

Go to **API service** → **"Variables"** and add:

#### Required (Production)
```
# Application
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# Database (auto-generated, just reference it)
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Redis (auto-generated, just reference it)
CELERY_BROKER_URL=${{Redis.REDIS_URL}}/1
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}/2

# Security (MUST GENERATE UNIQUE VALUES)
SECRET_KEY=<generate-strong-key>
TOKEN_ENCRYPTION_KEY=<generate-fernet-key>
PHI_ENCRYPTION_KEY=<generate-fernet-key>

# Google OAuth (your credentials)
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_CLIENT_SECRET=<your-google-client-secret>
GOOGLE_REDIRECT_URI=https://<railway-domain>/api/v1/auth/google/callback

# Frontend URL (will update after deployment)
FRONTEND_BASE_URL=https://<railway-frontend-domain>
BACKEND_CORS_ORIGINS=https://<railway-frontend-domain>

# Notion (leave empty for demo)
NOTION_API_KEY=
NOTION_ROOT_PAGE_ID=

# Anthropic (leave empty for demo)
ANTHROPIC_API_KEY=
ANTHROPIC_BAA_SIGNED=false
```

### Step 3: Generate Secure Keys

In your terminal (local, not Railway):

```bash
# Generate SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate TOKEN_ENCRYPTION_KEY (Fernet)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate PHI_ENCRYPTION_KEY (Fernet)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy these values into Railway variables.

### Step 4: Configure Worker & Beat Services

Both **Worker** and **Beat** services need the same environment variables.

Go to **Worker service** → **"Variables"** and add:
```
DATABASE_URL=${{Postgres.DATABASE_URL}}
CELERY_BROKER_URL=${{Redis.REDIS_URL}}/1
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}/2
ENVIRONMENT=production
DEBUG=false
ANTHROPIC_API_KEY=<same-as-api>
ANTHROPIC_BAA_SIGNED=false
# (all other vars same as API)
```

Repeat for **Beat service**.

---

## Part 4: Configure Google OAuth Redirect URIs

### Get Your Railway Domain

After deploying the API service, Railway assigns a domain like:
```
https://firstmed-ai-api-prod-xxxx.railway.app
```

Find it in **API service** → **"Deployments"** → **Domain**

### Update Google OAuth Console

1. Go to https://console.cloud.google.com/apis/credentials
2. Find your OAuth 2.0 Client
3. Edit → **"Authorized redirect URIs"**
4. Add:
   ```
   https://<railway-api-domain>/api/v1/auth/google/callback
   ```
5. Save

**Example**:
```
https://firstmed-ai-api-prod-xxxx.railway.app/api/v1/auth/google/callback
```

---

## Part 5: Deploy Services

### Step 1: Connect Services

In Railway dashboard:
1. Go to **API service** → **"Connect"**
2. Select **PostgreSQL** service
3. Select **Redis** service
4. Click **"Connect"**

Repeat for **Worker** and **Beat** services.

### Step 2: Trigger Initial Deployment

1. Go to **API service** → **"Deployments"**
2. Click **"Deploy"** (or new commit to GitHub auto-deploys)
3. Watch logs for:
   ```
   [*] Running migrations...
   [*] Alembic upgrade successful
   [*] Uvicorn running on http://0.0.0.0:8000
   ```

### Step 3: Monitor Worker & Beat Startup

**Worker logs** should show:
```
[*] celery@railway worker running
[*] Connected to redis://...
[*] Ready to accept tasks
```

**Beat logs** should show:
```
[*] Celery beat started
[*] Scheduler running
```

---

## Part 6: Test the Deployment

### Test 1: API Health Check

```bash
curl https://<railway-api-domain>/health
```

**Expected**:
```json
{"status": "ok"}
```

### Test 2: API Docs

Open browser:
```
https://<railway-api-domain>/docs
```

**Expected**: Swagger UI (interactive API docs)

### Test 3: Database Connection

Railway PostgreSQL should be running. Verify via logs:
```
[*] Database connected
```

### Test 4: Redis Connection

Worker logs should show:
```
[*] Connected to redis://...
```

---

## Part 7: Deploy Frontend (Next.js)

### Option A: Deploy Frontend Separately (Recommended)

Deploy Next.js frontend to Vercel or Railway:

**Vercel** (easier for Next.js):
1. Go to https://vercel.com
2. Import your GitHub repo
3. Set `NEXT_PUBLIC_API_URL` = `https://<railway-api-domain>`
4. Deploy

**Railway** (same platform):
1. In Railway, click **"+ Add Service"** → **"GitHub repo"**
2. Select `frontend` directory
3. Set environment variable:
   ```
   NEXT_PUBLIC_API_URL=https://<railway-api-domain>
   ```
4. Deploy

### Option B: Deploy via Procfile

In Railway, if you want frontend on same project:

1. Uncomment in `Procfile`:
   ```
   web: cd frontend && npm run build && npm start
   ```
2. Add service to Railway:
   - **"+ Add Service"** → **"GitHub repo"**
   - Select `frontend` directory
   - Set `NEXT_PUBLIC_API_URL=${{api.RAILWAY_PUBLIC_DOMAIN}}`

---

## Part 8: Live Testing Checklist

### Email Sync Test

1. **Open frontend**: https://<railway-frontend-domain>
2. **Sign in** with Google (uses your credentials)
3. **Send test email** to your Gmail:
   ```
   Subject: Test email - MRI pricing
   Body: How much does an MRI scan cost?
   ```
4. **Click "Sync Gmail"** in dashboard
5. **Check Celery worker logs** for task execution:
   ```
   [*] Task workflow.pull_gmail_task[...] received
   [*] Task workflow.pull_gmail_task[...] succeeded
   ```
6. **View Reviews** → email should appear with draft

### Safety Gate Test

Send an appointment email:
```
Subject: Schedule an appointment
Body: I'd like to book an appointment for next Tuesday
```

**Expected**: No draft, status = `ROUTE_TO_STAFF`

### Emergency Test

Send an emergency email:
```
Subject: Help - chest pain
Body: I'm experiencing severe chest pain
```

**Expected**: No draft, status = `NEEDS_PHYSICIAN_REVIEW`

---

## Monitoring & Logs

### View Logs in Railway

**API Service**:
- Go to **API service** → **"Logs"**
- Filter by time, search for errors

**Worker Service**:
- Go to **Worker service** → **"Logs"**
- Should show task execution logs

**Beat Service**:
- Go to **Beat service** → **"Logs"**
- Shows periodic task scheduling

### Common Issues

| Issue | Solution |
|-------|----------|
| **API won't start** | Check DATABASE_URL, CELERY_BROKER_URL in variables |
| **Worker stuck in PENDING** | Check Redis connection (logs should show error) |
| **Migrations fail** | Ensure DATABASE_URL is correct, PostgreSQL is running |
| **OAuth fails** | Verify GOOGLE_REDIRECT_URI matches Railway domain |
| **Frontend can't reach API** | Check NEXT_PUBLIC_API_URL and BACKEND_CORS_ORIGINS |

---

## Production Checklist

### Before Sharing with Client

- [ ] API service deployed and healthy
- [ ] PostgreSQL database running
- [ ] Redis cache running
- [ ] Celery worker running (shows "Ready to accept tasks")
- [ ] Celery beat running (shows "Scheduler running")
- [ ] Google OAuth credentials configured
- [ ] Redirect URI updated in Google Console
- [ ] Frontend deployed (Vercel or Railway)
- [ ] FRONTEND_BASE_URL and BACKEND_CORS_ORIGINS match
- [ ] Email sync test passed
- [ ] Safety gates verified (appointments blocked, emergencies escalated)
- [ ] All 272 tests still passing locally
- [ ] Database migrations applied (log shows "Alembic upgrade successful")
- [ ] No errors in API, Worker, or Beat logs

---

## Share with Client

Once verified, share these links:

1. **Frontend URL**: `https://<railway-frontend-domain>`
   - They test here as end-users
2. **API Docs** (optional): `https://<railway-api-domain>/docs`
   - Technical reference

---

## Cost Estimate (Railway Free Tier)

Railway free tier includes:
- ✅ 500 hours/month compute
- ✅ 5GB database
- ✅ 5GB Redis
- ✅ Up to 3 services

**For this project**: ~$0-10/month on free tier (with sleep during inactivity)

**For production**: ~$50-150/month depending on scale

---

## Next Steps After Client Testing

1. **Collect Feedback**: Ask client about UX, features, workflows
2. **Notion Setup**: Get client's Notion API key + database ID
3. **Anthropic Setup**: Discuss AI drafting, get BAA signed
4. **Custom Domain**: Set up clinic's domain (e.g., `app.clinic.com`)
5. **Production Hardening**: Add monitoring, backups, on-call setup

---

## Troubleshooting

### Deployment Fails

Check Deployment logs:
1. API service → Deployments → Recent deployment
2. Click deployment → "Logs"
3. Look for red error messages
4. Common: Missing env vars, GitHub clone failed

### Database Migrations Don't Run

Ensure Dockerfile includes:
```dockerfile
CMD ["sh", "-c", "alembic upgrade head && uvicorn ..."]
```

### Celery Tasks Not Processing

1. Check Worker service is running (not failed)
2. Check Worker logs for Redis connection errors
3. Verify `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` in Worker variables

### Frontend Can't Reach API

1. Verify `NEXT_PUBLIC_API_URL` in frontend deployment
2. Verify `BACKEND_CORS_ORIGINS` in API service
3. Both should match the actual Railway domains

---

## Support

- Railway Docs: https://docs.railway.app
- Community: https://discord.gg/railway
- GitHub Issues: https://github.com/abdul888-888/firstmed-ai-email-assistant/issues

---

## Sign-Off

Once all checks pass:

**Railway Deployment Status**: ✅ READY FOR CLIENT TESTING

**API Domain**: https://<railway-api-domain>  
**Frontend Domain**: https://<railway-frontend-domain>  
**Date Deployed**: ________________  
**Deployed By**: ________________  
