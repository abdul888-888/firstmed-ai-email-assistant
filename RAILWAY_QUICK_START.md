# Railway Deployment — Quick Start Checklist

**TL;DR**: Deploy to Railway in 15 minutes.

---

## ✅ Pre-Deployment (Local)

- [ ] Repository pushed to GitHub
- [ ] All tests passing locally (`pytest` → 272/272)
- [ ] Google OAuth Client ID & Secret ready

---

## 🚀 Railway Setup (5 minutes)

### 1. Create Project & Link GitHub
1. Go to https://railway.app
2. **"New Project"** → **"Deploy from GitHub"**
3. Select: `abdul888-888/firstmed-ai-email-assistant`
4. Click **"Deploy Now"**

### 2. Add PostgreSQL
1. **"+ Add Service"** → **"Database"** → **"PostgreSQL"**
2. Create
3. Copy `DATABASE_URL` (shown in service variables)

### 3. Add Redis
1. **"+ Add Service"** → **"Database"** → **"Redis"**
2. Create
3. Copy `REDIS_URL` (shown in service variables)

---

## ⚙️ Configure Environment Variables (5 minutes)

### Generate Secure Keys (Local Terminal)

```bash
# SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"

# TOKEN_ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# PHI_ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Set Variables in Each Service

**API Service → Variables**:
```
ENVIRONMENT=production
DATABASE_URL=${{Postgres.DATABASE_URL}}
CELERY_BROKER_URL=${{Redis.REDIS_URL}}/1
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}/2
SECRET_KEY=<paste-generated-key>
TOKEN_ENCRYPTION_KEY=<paste-generated-key>
PHI_ENCRYPTION_KEY=<paste-generated-key>
GOOGLE_CLIENT_ID=<your-client-id>
GOOGLE_CLIENT_SECRET=<your-client-secret>
FRONTEND_BASE_URL=https://<railway-frontend-domain>
BACKEND_CORS_ORIGINS=https://<railway-frontend-domain>
```

**Worker Service → Variables**: Same as API (copy all)

**Beat Service → Variables**: Same as API (copy all)

---

## 🔐 Update Google OAuth

After API deploys, get the domain:
- **API service** → **"Settings"** → **"Domains"**
- Copy: `https://firstmed-ai-api-xxxx.railway.app`

Go to Google Console:
1. https://console.cloud.google.com/apis/credentials
2. Edit OAuth client
3. Add Authorized redirect URI:
   ```
   https://firstmed-ai-api-xxxx.railway.app/api/v1/auth/google/callback
   ```

---

## 🚢 Deploy (3 minutes)

1. **API Service**: Click **"Deploy"**
   - Wait for ✅ green checkmark
   - Check logs: `"Alembic upgrade successful"` & `"Uvicorn running"`

2. **Worker Service**: Click **"Deploy"**
   - Check logs: `"[*] celery@... ready"`

3. **Beat Service**: Click **"Deploy"**
   - Check logs: `"[*] Celery beat started"`

---

## ✅ Verify Deployment (2 minutes)

```bash
# Test API health
curl https://<api-domain>/health
# Expected: {"status":"ok"}

# Test API docs
# Open: https://<api-domain>/docs
# Expected: Swagger UI loads
```

---

## 🧪 Live Email Test (3 minutes)

### If Frontend on Vercel
1. Open frontend: https://<vercel-domain>
2. Sign in with Google
3. Send test email to Gmail
4. Click "Sync Gmail"
5. Check Celery worker logs for task execution
6. View Reviews → email appears with draft

### If Frontend on Railway
1. Open frontend: https://<railway-frontend-domain>
2. Same as above

---

## 📊 Test Safety Gates

**Appointment Request** (should NOT draft):
- Subject: `Schedule an appointment`
- Body: `I'd like to book an appointment`
- Expected: Status = `ROUTE_TO_STAFF`, no draft

**Emergency** (should NOT draft):
- Subject: `Help - chest pain`
- Body: `I'm experiencing severe chest pain`
- Expected: Status = `NEEDS_PHYSICIAN_REVIEW`, no draft

**Normal Question** (SHOULD draft):
- Subject: `MRI pricing`
- Body: `How much does an MRI scan cost?`
- Expected: Status = `ADMIN_DIRECT_REPLY`, draft generated

---

## 🎉 Share with Client

Once all tests pass:

```
Email to client:
---
Hi [Client],

Your FirstMed AI Email Assistant is live for testing!

📱 Frontend: https://<your-domain>
📊 API Docs: https://<api-domain>/docs

Please sign in with Google and test the following:
1. Sync Gmail emails
2. Review draft responses
3. Test safety gates (try scheduling an appointment - it should be blocked)

Any feedback: reply to this email or create an issue on GitHub.

Thanks!
---
```

---

## 🚨 Troubleshooting (If Needed)

| Problem | Fix |
|---------|-----|
| **API won't deploy** | Check all variables are set. Logs → see specific error |
| **Worker won't start** | Verify CELERY_BROKER_URL references Redis correctly |
| **OAuth redirect fails** | Verify Google Console has exact Railway domain |
| **No emails syncing** | Check Worker logs for "Connected to redis://..." |

See `RAILWAY_DEPLOYMENT_GUIDE.md` for detailed troubleshooting.

---

## 📚 Detailed Docs

- `RAILWAY_DEPLOYMENT_GUIDE.md` — Full step-by-step (with screenshots references)
- `RAILWAY_ENV_TEMPLATE.md` — All env variables explained
- `Procfile` — Service definitions
- `Dockerfile` — Container build config

---

## ⏱️ Total Time

- Setup: 5 min
- Variables: 5 min
- Deploy: 3 min
- Test: 2 min
- **Total: ~15 minutes**

---

## Next Steps After Client Testing

1. Collect feedback
2. Implement changes locally
3. Push to GitHub → auto-redeploys
4. Share updated version with client
5. Get Notion API key + Anthropic API key when client is ready
6. Set up custom domain (clinic's domain)

---

**Status**: Ready to deploy! 🚀
