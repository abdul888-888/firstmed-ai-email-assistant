# Railway Deployment Fix - Step by Step

## Current Problem
Your backend container on Railway is crashing with `KeyError: '0013'` because the Docker image contains broken migration files. The fixed code is in your Git repo, but Railway hasn't rebuilt the image yet.

## Step-by-Step Fix

### Step 1: Get Your Database Credentials
1. Go to [railway.app](https://railway.app)
2. Select your project
3. Click the **PostgreSQL** service in the Environment
4. Go to **Variables** tab
5. Copy the `DATABASE_URL` value

It looks like: `postgresql://user:password@host:5432/dbname`

### Step 2: Mark Migrations as Complete

**Option A: Using psql (if you have PostgreSQL client installed locally)**

```bash
# Replace with your actual DATABASE_URL from Railway
psql "postgresql://user:password@host:5432/dbname" -c \
  "INSERT INTO alembic_version (version_num, is_primary) VALUES ('0013', true), ('0014', true) ON CONFLICT (version_num) DO NOTHING;"
```

**Option B: Using Railway CLI (easier if you have it installed)**

```bash
# Login to Railway
railway login

# Connect to your project
railway link

# Run the fix command
railway run psql -c \
  "INSERT INTO alembic_version (version_num, is_primary) VALUES ('0013', true), ('0014', true) ON CONFLICT (version_num) DO NOTHING;"
```

**Option C: Using DBeaver or PgAdmin (GUI approach)**

If you have a database client:
1. Connect using the DATABASE_URL
2. Open a query window
3. Run this SQL:
```sql
INSERT INTO alembic_version (version_num, is_primary) 
VALUES ('0013', true), ('0014', true)
ON CONFLICT (version_num) DO NOTHING;

-- Verify it worked
SELECT version_num FROM alembic_version ORDER BY version_num;
```

---

### Step 3: Rebuild the Docker Image on Railway

#### Option A: Push Code Changes (Triggers Auto-Rebuild)

The simplest approach — just push any small change to trigger Railway to rebuild:

```bash
# Make a small change to a file (e.g., add a comment)
# Then commit and push
git add .
git commit -m "Trigger Railway rebuild with fixed migrations"
git push origin main
```

Railway will automatically:
1. Detect the new push
2. Rebuild the Docker image with the fixed migration files
3. Deploy the new image

**Watch the deployment:**
- Go to Railway dashboard
- Click your API service
- Click "Deployments" tab
- You should see a new deployment starting (blue dot = building, green = deployed)

#### Option B: Manually Trigger Rebuild via Railway UI

1. Go to Railway dashboard
2. Select your **API service**
3. Click the three-dot menu (⋮) in the top right
4. Select **"Redeploy"** or **"Open Deploy Menu"**
5. Click the deploy button

#### Option C: Using Railway CLI

```bash
# Make sure you're in the project directory
cd c:\Users\HP\firstmed-ai-email-assistant

# Link to your Railway project
railway link

# Deploy (triggers rebuild)
railway deploy
```

---

### Step 4: Verify the Fix Worked

**Check 1: Database has migrations marked**
```bash
psql "postgresql://user:password@host:5432/dbname" -c \
  "SELECT version_num FROM alembic_version WHERE version_num IN ('0013', '0014');"
```

You should see:
```
version_num
-----------
0013
0014
```

**Check 2: Watch deployment logs**

Go to Railway dashboard → API service → **Logs** tab

You should see:
```
INFO  [alembic.runtime.migration] Running upgrade 0013 -> 0014, Drop google_credentials table
INFO  [alembic.runtime.migration] Done.
INFO  [uvicorn.server] Started server process
```

**Check 3: API is healthy**

```bash
curl https://your-railway-api-domain.com/health
```

Should return:
```json
{"status":"ok"}
```

Or check in Railway dashboard — the API service should have a **green status indicator**.

---

## Recommended Approach (Easiest)

**For you, the fastest fix is:**

1. **Mark migrations in database** (Option A or B above with psql)
2. **Push to Git** to trigger rebuild:
   ```bash
   git add .
   git commit -m "Deploy: fix Alembic migrations"
   git push origin main
   ```
3. **Watch deployment** in Railway UI (should take 2-5 minutes)
4. **Verify** health check passes

---

## Troubleshooting

### "psql: command not found"
- You don't have PostgreSQL client installed
- Use **Railway CLI** instead: `railway run psql -c "..."`
- Or use a GUI like DBeaver/PgAdmin

### Deployment still fails after fix
- The build might be cached
- Go to API service → Settings → scroll to "Deployment Triggers"
- Change "Watch Paths" or click "Redeploy" to force a full rebuild
- If still stuck: delete the old build and redeploy

### "duplicate key value violates unique constraint"
- Migrations 0013/0014 were already marked complete
- Run this to check:
  ```sql
  SELECT version_num FROM alembic_version ORDER BY version_num;
  ```
- If you see 0013 and 0014, you're good — just redeploy

### "KeyError: '0013'" still appears
- The new image hasn't been deployed yet
- Check Railway Deployments tab — is there a recent green deployment?
- If the old red deployment is still active, Railway is still running the old image
- Click "Redeploy" to force the new image to become active

### Cannot connect to database
- Check DATABASE_URL is correct
- Verify PostgreSQL service is running in Railway (should have green status)
- Make sure your IP has access (Railway allows internal only by default, but CLI bypasses this)

---

## What This Does

| Step | Action | Result |
|------|--------|--------|
| Mark migrations | INSERT into alembic_version | Alembic knows 0013/0014 are done, won't try to re-parse the broken migration files |
| Push to Git | `git push` | Railway detects change, rebuilds Docker image with fixed migration files from your code |
| Redeploy | New image starts | Alembic loads the new fixed migrations, skips 0013/0014 (already marked), container starts successfully |

---

## Files for Reference

I've created these guides in your repo for future reference:
- `QUICK_FIX_COMMANDS.md` — One-liner commands for any environment
- `ALEMBIC_MIGRATION_RECOVERY.md` — Comprehensive recovery guide
- `fix_migrations.sql` — SQL script you can run directly

---

## Next Steps After This is Fixed

Once the container is running:

1. **Test Claude integration** with an email to verify confidence scores are now high (0.75–0.95)
2. **Check draft generation** — should now work for routine admin emails
3. **Monitor logs** for any other issues

Your API should be fully functional with Claude properly integrated!
