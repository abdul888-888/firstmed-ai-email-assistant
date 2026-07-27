# Railway Exact Configuration — Copy & Paste

**For Your Friend**: Use this to configure Railway services.

---

## Environment Variables to Paste into Railway

### Step 1: Your Friend Pastes into API Service → Variables

```
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
DATABASE_URL=${{Postgres.DATABASE_URL}}
CELERY_BROKER_URL=${{Redis.REDIS_URL}}/1
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}/2
SECRET_KEY=<YOU-WILL-REPLACE>
TOKEN_ENCRYPTION_KEY=<YOU-WILL-REPLACE>
PHI_ENCRYPTION_KEY=<YOU-WILL-REPLACE>
GOOGLE_CLIENT_ID=<YOU-WILL-REPLACE>
GOOGLE_CLIENT_SECRET=<YOU-WILL-REPLACE>
GOOGLE_REDIRECT_URI=<YOU-WILL-FILL-LATER>
FRONTEND_BASE_URL=<YOU-WILL-FILL-LATER>
BACKEND_CORS_ORIGINS=<YOU-WILL-FILL-LATER>
NOTION_API_KEY=
NOTION_ROOT_PAGE_ID=
ANTHROPIC_API_KEY=
ANTHROPIC_BAA_SIGNED=false
API_V1_PREFIX=/api/v1
ACCESS_TOKEN_EXPIRE_MINUTES=60
ALGORITHM=HS256
GMAIL_AUTO_PULL_INTERVAL_SECONDS=300
```

### Step 2: Your Friend Pastes Same into Worker Service → Variables

(Copy all variables from API service, paste into Worker)

### Step 3: Your Friend Pastes Same into Beat Service → Variables

(Copy all variables from API service, paste into Beat)

---

## You Generate These Locally & Send to Friend

### Generate Keys (run in your terminal):

```bash
# Command 1
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Command 2
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Command 3
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Send Your Friend This Template (filled in with outputs):

```
SECRET_KEY = <PASTE-OUTPUT-OF-COMMAND-1>
TOKEN_ENCRYPTION_KEY = <PASTE-OUTPUT-OF-COMMAND-2>
PHI_ENCRYPTION_KEY = <PASTE-OUTPUT-OF-COMMAND-3>
GOOGLE_CLIENT_ID = <YOUR-GOOGLE-CLIENT-ID>
GOOGLE_CLIENT_SECRET = <YOUR-GOOGLE-CLIENT-SECRET>
```

### Your Friend Updates in Railway:

Go to API Service → Variables and replace:
- `SECRET_KEY=<YOU-WILL-REPLACE>` → `SECRET_KEY=<value-you-sent>`
- `TOKEN_ENCRYPTION_KEY=<YOU-WILL-REPLACE>` → `TOKEN_ENCRYPTION_KEY=<value-you-sent>`
- `PHI_ENCRYPTION_KEY=<YOU-WILL-REPLACE>` → `PHI_ENCRYPTION_KEY=<value-you-sent>`
- `GOOGLE_CLIENT_ID=<YOU-WILL-REPLACE>` → `GOOGLE_CLIENT_ID=<value-you-sent>`
- `GOOGLE_CLIENT_SECRET=<YOU-WILL-REPLACE>` → `GOOGLE_CLIENT_SECRET=<value-you-sent>`

Then copy these updated variables to Worker & Beat services.

---

## After API Service Deployed

### Your Friend Gets API Domain

1. Go to **API service** → **"Settings"** → **"Domains"**
2. Copy the domain (example: `https://firstmed-ai-api-prod-xxxx.railway.app`)
3. Send to you

### You Update Google OAuth Console

Go to https://console.cloud.google.com/apis/credentials

Edit your OAuth 2.0 Client ID → Add to **Authorized redirect URIs**:

```
https://<API-DOMAIN-YOUR-FRIEND-SENT>/api/v1/auth/google/callback
```

**Example** (if friend sent `https://firstmed-ai-api-prod-abc123.railway.app`):
```
https://firstmed-ai-api-prod-abc123.railway.app/api/v1/auth/google/callback
```

### You Update GOOGLE_REDIRECT_URI in Railway

1. Go to API service → **"Variables"**
2. Find: `GOOGLE_REDIRECT_URI=<YOU-WILL-FILL-LATER>`
3. Replace with: `GOOGLE_REDIRECT_URI=https://<API-DOMAIN-YOUR-FRIEND-SENT>/api/v1/auth/google/callback`
4. Do same for Worker & Beat services

---

## After Frontend Deployed (Vercel or Railway)

### Your Friend Gets Frontend Domain

(If deployed to Vercel): `https://your-vercel-domain.vercel.app`
(If deployed to Railway): Railway will provide domain

Send to you.

### You Update Frontend URLs in Railway

Go to API service → **"Variables"**

Replace:
- `FRONTEND_BASE_URL=<YOU-WILL-FILL-LATER>` → `FRONTEND_BASE_URL=https://<FRONTEND-DOMAIN>`
- `BACKEND_CORS_ORIGINS=<YOU-WILL-FILL-LATER>` → `BACKEND_CORS_ORIGINS=https://<FRONTEND-DOMAIN>`

**Example** (if frontend is at `https://firstmed-frontend.vercel.app`):
```
FRONTEND_BASE_URL=https://firstmed-frontend.vercel.app
BACKEND_CORS_ORIGINS=https://firstmed-frontend.vercel.app
```

Do same for Worker & Beat services.

---

## Google OAuth Redirect URIs Summary

**Exact URIs you need to add to Google Cloud Console**:

```
https://<your-railway-api-domain>/api/v1/auth/google/callback
```

**Examples**:
```
https://firstmed-ai-api-prod-abc123.railway.app/api/v1/auth/google/callback
https://firstmed-ai-api-staging-xyz789.railway.app/api/v1/auth/google/callback
```

**Where to add**:
1. Google Cloud Console: https://console.cloud.google.com/apis/credentials
2. Find your OAuth 2.0 Client
3. Edit → "Authorized redirect URIs"
4. Add the URL above
5. Save

---

## Services to Deploy (in order)

1. **PostgreSQL** (Your friend adds via "+ Add Service" → Database → PostgreSQL)
2. **Redis** (Your friend adds via "+ Add Service" → Database → Redis)
3. **API service** (auto-detected from Procfile, your friend clicks "Deploy")
4. **Worker service** (auto-detected from Procfile, your friend clicks "Deploy")
5. **Beat service** (auto-detected from Procfile, your friend clicks "Deploy")
6. **Frontend** (optional: Vercel or Railway, you deploy or your friend adds)

---

## Verification Commands

**After all services deployed, test**:

```bash
# Test 1: API health
curl https://<railway-api-domain>/health

# Expected response:
# {"status":"ok"}

# Test 2: API docs (open in browser)
https://<railway-api-domain>/docs

# Expected: Swagger UI loads
```

---

## Quick Checklist for Your Friend

- [ ] Create Railway project from GitHub repo
- [ ] Add PostgreSQL database
- [ ] Add Redis database
- [ ] Paste environment variables into API, Worker, Beat services
- [ ] Wait for you to send secure keys + Google credentials
- [ ] Replace placeholders in variables with values you sent
- [ ] Deploy API service → watch logs for "Alembic upgrade successful"
- [ ] Deploy Worker service → watch logs for "[*] celery@... ready"
- [ ] Deploy Beat service → watch logs for "[*] Celery beat started"
- [ ] Send you the API domain when all 3 services are running
- [ ] Wait for you to update Google OAuth
- [ ] Wait for you to send updated GOOGLE_REDIRECT_URI variable
- [ ] Update GOOGLE_REDIRECT_URI in all 3 services
- [ ] (Optional) Deploy frontend to Vercel or Railway

---

## Your Checklist

- [ ] Generate 3 secure keys (run local Python commands)
- [ ] Send keys + Google credentials to friend
- [ ] Wait for friend to send API domain
- [ ] Update Google OAuth Console with redirect URI
- [ ] Send friend the updated GOOGLE_REDIRECT_URI variable
- [ ] Friend updates GOOGLE_REDIRECT_URI in all 3 services
- [ ] Deploy frontend (Vercel or Railway)
- [ ] Send friend frontend domain
- [ ] Update FRONTEND_BASE_URL and BACKEND_CORS_ORIGINS in all 3 services
- [ ] Test email sync end-to-end
- [ ] Share live URL with client

---

**Status**: Ready to deploy! Send the top section of this file to your friend. 🚀
