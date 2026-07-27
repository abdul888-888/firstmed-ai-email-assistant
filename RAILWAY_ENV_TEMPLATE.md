# Railway Environment Variables Template

Copy and paste these into each Railway service's **"Variables"** section.

---

## API Service Variables

```
# Application
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# Database (from PostgreSQL plugin - use reference)
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Redis (from Redis plugin - use reference)
CELERY_BROKER_URL=${{Redis.REDIS_URL}}/1
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}/2

# Security (GENERATE THESE LOCALLY)
SECRET_KEY=<run: python -c "import secrets; print(secrets.token_urlsafe(32))">
TOKEN_ENCRYPTION_KEY=<run: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
PHI_ENCRYPTION_KEY=<run: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

# Google OAuth (from Google Cloud Console)
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_CLIENT_SECRET=<your-google-client-secret>
GOOGLE_REDIRECT_URI=https://<railway-api-domain>/api/v1/auth/google/callback

# Frontend URLs (update after frontend deployment)
FRONTEND_BASE_URL=https://<railway-frontend-domain>
BACKEND_CORS_ORIGINS=https://<railway-frontend-domain>

# Notion (leave empty for demo, add when client provides)
NOTION_API_KEY=
NOTION_ROOT_PAGE_ID=

# Anthropic (leave empty for demo, add when ready)
ANTHROPIC_API_KEY=
ANTHROPIC_BAA_SIGNED=false

# API Configuration
API_V1_PREFIX=/api/v1
ACCESS_TOKEN_EXPIRE_MINUTES=60
ALGORITHM=HS256

# Feature Flags
GMAIL_AUTO_PULL_INTERVAL_SECONDS=300
```

---

## Worker Service Variables

**Copy all variables from API service above**, only difference:
- Worker doesn't need `FRONTEND_BASE_URL` or `BACKEND_CORS_ORIGINS`
- Worker needs everything else (DB, Redis, secrets, OAuth)

```
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
DATABASE_URL=${{Postgres.DATABASE_URL}}
CELERY_BROKER_URL=${{Redis.REDIS_URL}}/1
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}/2
SECRET_KEY=<same-as-api>
TOKEN_ENCRYPTION_KEY=<same-as-api>
PHI_ENCRYPTION_KEY=<same-as-api>
GOOGLE_CLIENT_ID=<same-as-api>
GOOGLE_CLIENT_SECRET=<same-as-api>
NOTION_API_KEY=
NOTION_ROOT_PAGE_ID=
ANTHROPIC_API_KEY=
ANTHROPIC_BAA_SIGNED=false
```

---

## Beat Service Variables

**Same as Worker service** (Beat is part of Celery).

```
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
DATABASE_URL=${{Postgres.DATABASE_URL}}
CELERY_BROKER_URL=${{Redis.REDIS_URL}}/1
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}/2
SECRET_KEY=<same-as-api>
TOKEN_ENCRYPTION_KEY=<same-as-api>
PHI_ENCRYPTION_KEY=<same-as-api>
GOOGLE_CLIENT_ID=<same-as-api>
GOOGLE_CLIENT_SECRET=<same-as-api>
NOTION_API_KEY=
NOTION_ROOT_PAGE_ID=
ANTHROPIC_API_KEY=
ANTHROPIC_BAA_SIGNED=false
GMAIL_AUTO_PULL_INTERVAL_SECONDS=300
```

---

## Frontend Service Variables (if deploying to Railway)

```
NEXT_PUBLIC_API_URL=https://<railway-api-domain>
NODE_ENV=production
```

---

## How to Generate Secure Keys

### SECRET_KEY
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```
Output: `abc123...` (copy this into Railway)

### TOKEN_ENCRYPTION_KEY (Fernet)
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Output: `gAAAAABn...==` (copy this into Railway)

### PHI_ENCRYPTION_KEY (Fernet)
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Output: `gAAAAABn...==` (copy this into Railway)

**Generate these once and use same values across all services.**

---

## Google OAuth Credentials

1. Go to https://console.cloud.google.com/apis/credentials
2. Create OAuth 2.0 Client (if not already created)
3. Get:
   - `GOOGLE_CLIENT_ID` = Client ID
   - `GOOGLE_CLIENT_SECRET` = Client Secret
4. Add Authorized redirect URI:
   ```
   https://<your-railway-api-domain>/api/v1/auth/google/callback
   ```

---

## Finding Railway Service Domains

After deployment, find domains in Railway dashboard:

**API Service**:
- Go to **API service** → **"Settings"** → **"Domains"**
- Copy the public domain (e.g., `https://firstmed-ai-api-prod-xxxx.railway.app`)

**Frontend Service**:
- Go to **Frontend service** → **"Settings"** → **"Domains"**
- Copy the public domain (e.g., `https://firstmed-ai-frontend-xxxx.railway.app`)

---

## Railway References (for Postgres & Redis)

Railway auto-creates variables and you reference them:

```
${{Postgres.DATABASE_URL}}     ← Postgres connection string
${{Redis.REDIS_URL}}          ← Redis connection string
```

These are available in Railway's variable templating. No need to manually set them.

---

## Verification After Setting Variables

After adding all variables to each service:

1. **API Service**: Deploy → Check logs for "Database connected"
2. **Worker Service**: Watch logs for "[*] celery@... ready"
3. **Beat Service**: Watch logs for "[*] Celery beat started"
4. **Test**: `curl https://<api-domain>/health` → should return 200

---

## Updating Variables Later

If you need to update (e.g., new Google credentials):

1. Go to service → **"Variables"**
2. Edit the variable
3. Railway auto-redeploys with new values
4. Check logs to confirm

No manual restart needed.

---

## Security Best Practices

- ✅ Never commit `.env` or secrets to git
- ✅ Use Railway's built-in variable encryption
- ✅ Rotate encryption keys every 90 days (set reminders)
- ✅ Don't share secrets in Slack/email
- ✅ Use separate keys for staging vs production

---

## Common Issues

| Issue | Fix |
|-------|-----|
| **"Invalid DATABASE_URL"** | Use `${{Postgres.DATABASE_URL}}` reference, don't hardcode |
| **"Redis connection refused"** | Use `${{Redis.REDIS_URL}}/1` reference |
| **"OAuth redirect_uri mismatch"** | Update Google Console with exact Railway domain |
| **"SECRET_KEY must be a string"** | Make sure value doesn't have special characters that break Railway parsing |

---

## Ready to Deploy?

Once all variables are set:

1. ✅ Click **"Deploy"** on each service
2. ✅ Watch logs for successful startup
3. ✅ Run live email test
4. ✅ Share with client!
