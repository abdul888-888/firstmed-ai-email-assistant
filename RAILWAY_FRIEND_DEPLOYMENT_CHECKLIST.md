# Railway Deployment Checklist for Friend

**Deploying**: abdul888-888/firstmed-ai-email-assistant  
**Your Role**: Paste environment variables, update Google OAuth  
**Estimated Time**: 20 minutes

---

## ✅ Pre-Deployment Verification

**Status**: ✅ Repository is ready
- ✅ Procfile configured (3 services: api, worker, beat)
- ✅ Dockerfile production-ready
- ✅ railway.json configured
- ✅ 272 tests passing
- ✅ All code committed to GitHub

---

## 🚀 Step-by-Step Deployment

### Step 1: Create Railway Project & Link GitHub (2 min)

**Your Friend Does**:
1. Go to https://railway.app
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Authorize Railway to access GitHub
4. Select repo: **`abdul888-888/firstmed-ai-email-assistant`**
5. Click **"Deploy Now"**

**Expected**: Railway clones repo, auto-detects `Procfile`, creates 3 services

---

### Step 2: Add PostgreSQL Database (1 min)

**Your Friend Does**:
1. Click **"+ Add Service"**
2. Select **"Database"** → **"PostgreSQL"**
3. Confirm and create

**Expected**: PostgreSQL running, `DATABASE_URL` auto-generated

---

### Step 3: Add Redis Database (1 min)

**Your Friend Does**:
1. Click **"+ Add Service"**
2. Select **"Database"** → **"Redis"**
3. Confirm and create

**Expected**: Redis running, `REDIS_URL` auto-generated

---

### Step 4: Configure API Service Environment Variables (5 min)

**Your Friend Does**:
1. Go to **API service** → **"Variables"**
2. Click **"+ Add Variable"** for each line below
3. Paste **exactly** as shown:

```
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

DATABASE_URL=${{Postgres.DATABASE_URL}}
CELERY_BROKER_URL=${{Redis.REDIS_URL}}/1
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}/2

SECRET_KEY=<PLACEHOLDER-REPLACE-BELOW>
TOKEN_ENCRYPTION_KEY=<PLACEHOLDER-REPLACE-BELOW>
PHI_ENCRYPTION_KEY=<PLACEHOLDER-REPLACE-BELOW>

GOOGLE_CLIENT_ID=<PLACEHOLDER-REPLACE-BELOW>
GOOGLE_CLIENT_SECRET=<PLACEHOLDER-REPLACE-BELOW>
GOOGLE_REDIRECT_URI=<PLACEHOLDER-WILL-FILL-LATER>

FRONTEND_BASE_URL=<PLACEHOLDER-WILL-FILL-LATER>
BACKEND_CORS_ORIGINS=<PLACEHOLDER-WILL-FILL-LATER>

NOTION_API_KEY=
NOTION_ROOT_PAGE_ID=
ANTHROPIC_API_KEY=
ANTHROPIC_BAA_SIGNED=false

API_V1_PREFIX=/api/v1
ACCESS_TOKEN_EXPIRE_MINUTES=60
ALGORITHM=HS256
GMAIL_AUTO_PULL_INTERVAL_SECONDS=300
```

**Next Section**: You need to provide the `<PLACEHOLDER>` values

---

### Step 5: You Provide Secure Keys & Google Credentials

**You Do Locally** (run these commands):

```bash
# Generate SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate TOKEN_ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate PHI_ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**You Send to Your Friend**:
```
SECRET_KEY = <output from first command>
TOKEN_ENCRYPTION_KEY = <output from second command>
PHI_ENCRYPTION_KEY = <output from third command>
GOOGLE_CLIENT_ID = <your-google-client-id>
GOOGLE_CLIENT_SECRET = <your-google-client-secret>
```

**Your Friend Updates in Railway**:
1. Go to **API service** → **"Variables"**
2. Find each variable above
3. Replace `<PLACEHOLDER-REPLACE-BELOW>` with the values you provided

---

### Step 6: Configure Worker Service Variables (2 min)

**Your Friend Does**:
1. Go to **Worker service** → **"Variables"**
2. Add **all the same variables** from API service above
3. Copy-paste entire list (same values for everything)

---

### Step 7: Configure Beat Service Variables (1 min)

**Your Friend Does**:
1. Go to **Beat service** → **"Variables"**
2. Add **all the same variables** from API service above
3. Copy-paste entire list (same values for everything)

---

### Step 8: Deploy Services (5 min)

**Your Friend Does**:
1. Go to **API service** → Click **"Deploy"**
   - Wait for ✅ green checkmark
   - Check logs for: `"Alembic upgrade successful"` and `"Uvicorn running"`
   
2. Go to **Worker service** → Click **"Deploy"**
   - Check logs for: `"[*] celery@... ready"`
   
3. Go to **Beat service** → Click **"Deploy"**
   - Check logs for: `"[*] Celery beat started"`

---

### Step 9: Get Railway Domains (1 min)

**Your Friend Does**:
1. Go to **API service** → **"Settings"** → **"Domains"**
2. Copy the public domain (looks like: `https://firstmed-ai-api-prod-xxxx.railway.app`)
3. Send to you

**You Get** (from your friend):
```
API_DOMAIN = https://firstmed-ai-api-prod-xxxx.railway.app
```

---

### Step 10: Update Google OAuth Redirect URIs (2 min)

**You Do** (in Google Cloud Console):
1. Go to https://console.cloud.google.com/apis/credentials
2. Find your OAuth 2.0 Client ID
3. Click **"Edit"**
4. In **"Authorized redirect URIs"**, add:
   ```
   https://<API_DOMAIN>/api/v1/auth/google/callback
   ```
   
   **Example**:
   ```
   https://firstmed-ai-api-prod-xxxx.railway.app/api/v1/auth/google/callback
   ```
5. Click **"Save"**

---

### Step 11: Deploy Frontend (Optional - Separate or on Railway)

**Option A: Deploy to Vercel** (Recommended for Next.js)
1. Go to https://vercel.com
2. Import GitHub repo
3. Set environment variable:
   ```
   NEXT_PUBLIC_API_URL=https://<API_DOMAIN>
   ```
4. Deploy

**Option B: Deploy to Railway** (Same project as backend)
1. **Your Friend** goes to Railway project
2. Click **"+ Add Service"** → **"GitHub repo"**
3. Select `abdul888-888/firstmed-ai-email-assistant` (frontend directory)
4. Set environment variable:
   ```
   NEXT_PUBLIC_API_URL=https://<API_DOMAIN>
   NODE_ENV=production
   ```
5. Click **"Deploy"**

**After Frontend Deployed**:
1. Get frontend domain from **"Settings"** → **"Domains"**
2. Update API service variables:
   ```
   FRONTEND_BASE_URL=https://<FRONTEND_DOMAIN>
   BACKEND_CORS_ORIGINS=https://<FRONTEND_DOMAIN>
   ```
3. API service auto-redeploys with new values

---

## 🧪 Verification Tests (3 min)

**Your Friend Tests**:

### Test 1: API Health
```bash
curl https://<API_DOMAIN>/health
```
**Expected Output**:
```json
{"status":"ok"}
```

### Test 2: API Docs (Open in Browser)
```
https://<API_DOMAIN>/docs
```
**Expected**: Swagger UI loads with interactive API documentation

### Test 3: Worker Status
- Go to **Worker service** → **"Logs"**
- Should show: `"[*] celery@... ready"`

### Test 4: Beat Status
- Go to **Beat service** → **"Logs"**
- Should show: `"[*] Celery beat started"`

### Test 5: Email Sync (Live Test)
1. Open frontend: `https://<FRONTEND_DOMAIN>`
2. Sign in with Google
3. Send test email to your Gmail:
   ```
   Subject: Test email - MRI pricing
   Body: How much does an MRI scan cost?
   ```
4. Click **"Sync Gmail"** button
5. Check **Worker logs** for:
   ```
   [*] Task workflow.pull_gmail_task[...] received
   [*] Task workflow.pull_gmail_task[...] succeeded
   ```
6. View **Reviews** dashboard → email appears with draft

---

## 📋 Communication with Your Friend

### Send Your Friend This:

**Subject**: Railway Deployment Ready - Follow Attached Checklist

**Message**:
```
Hi [Friend],

Thanks for helping me deploy! The repository is ready for Railway deployment.

Please follow the attached checklist step-by-step. It will take about 20 minutes.

Key points:
1. Create project, link GitHub, add PostgreSQL & Redis
2. Configure environment variables (I'll provide the secure keys)
3. Deploy 3 services: API, Worker, Beat
4. Get the API domain and send it to me
5. I'll update Google OAuth and send you the updated variables

Once done, we'll have a live instance running!

Thanks!
```

**Attach**: This file (`RAILWAY_FRIEND_DEPLOYMENT_CHECKLIST.md`)

### Send Your Friend These Values (After Step 5):

```
SECRET_KEY = [generated value]
TOKEN_ENCRYPTION_KEY = [generated value]
PHI_ENCRYPTION_KEY = [generated value]
GOOGLE_CLIENT_ID = [your-id]
GOOGLE_CLIENT_SECRET = [your-secret]
```

---

## ✅ Final Checklist

### Your Friend Completes:
- [ ] GitHub repo linked to Railway
- [ ] PostgreSQL added
- [ ] Redis added
- [ ] API service deployed
- [ ] Worker service deployed
- [ ] Beat service deployed
- [ ] All logs show successful startup
- [ ] API health check passes (curl test)
- [ ] Sends you the API domain

### You Complete:
- [ ] Generate 3 secure keys (run local commands)
- [ ] Send keys + Google credentials to friend
- [ ] Update Google OAuth redirect URI
- [ ] Deploy frontend (Vercel or Railway)
- [ ] Test email sync end-to-end
- [ ] Share frontend URL with client

---

## 🚨 Troubleshooting (If Needed)

| Issue | Solution |
|-------|----------|
| **API won't start** | Check DATABASE_URL variable is set correctly. Look at API logs for specific error. |
| **Worker won't run** | Verify CELERY_BROKER_URL and CELERY_RESULT_BACKEND variables are set. Check Worker logs. |
| **Beat won't start** | Same as Worker - verify Redis variables. Check Beat logs. |
| **OAuth fails** | Make sure GOOGLE_REDIRECT_URI matches exactly what's in Google Console. |
| **Migrations fail** | Check PostgreSQL is running. Logs should show specific database error. |

---

## 🎉 Success!

Once all tests pass, you have:
- ✅ Production-grade FastAPI backend
- ✅ Celery async task processing
- ✅ PostgreSQL database
- ✅ Redis cache
- ✅ Live email testing capability
- ✅ Ready for client testing

---

## 📞 Quick Reference

| What | Where |
|------|-------|
| **Your Role** | Provide keys, update Google OAuth, test frontend |
| **Friend's Role** | Create Railway project, paste variables, deploy services |
| **Total Time** | ~20 minutes |
| **Cost** | ~$0-10/month (free tier with sleep) |

---

## Next Steps After Deployment

1. ✅ Share frontend URL with client for testing
2. Get client feedback
3. Push fixes to GitHub (auto-redeploys)
4. When ready: Add client's Notion API key
5. When ready: Enable Anthropic AI drafting
6. When ready: Set up custom domain

---

**Status**: ✅ Ready to deploy!

Send this checklist to your friend and follow the steps. You should be live for client testing within 30 minutes. 🚀
