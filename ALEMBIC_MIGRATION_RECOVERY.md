# Alembic Migration Recovery Guide

## Problem Summary

Your backend container is crashing with `KeyError: '0013'` because:

1. **Old Docker image** contains migrations with broken revision IDs (e.g., `"0013_connected_accounts"` instead of `"0013"`)
2. **Alembic revision chain** is broken — it can't find revision `"0013"` because it's stored as `"0013_connected_accounts"`
3. **Fixed migrations** exist in your local code, but the stale Docker image can't parse them

## Why a Stale Docker Image Matters

When you rebuild the Docker image, it includes the **fixed migration files** from your codebase. But if your database has incomplete/failed migration records from an old deployment, Alembic gets confused about what's already applied.

**The real solution**: Mark the broken migrations as "complete" in the database so Alembic skips them and won't try to parse the broken revision IDs.

---

## Solution: Mark Migrations as Applied

### Step 1: Access Your Database

#### For Docker Compose (Local)
```bash
# Connect to the PostgreSQL container
docker exec -it firstmed-db psql -U firstmed -d firstmed
```

#### For Docker Compose Staging
```bash
docker exec -it firstmed-postgres-staging psql -U firstmed_user -d firstmed_staging
```

#### For Railway Production
```bash
# Get DB credentials from Railway dashboard, then connect via psql or any client
psql postgresql://username:password@hostname:5432/dbname
```

#### For SQLite (Development)
```bash
# If using SQLite, access the database file directly
sqlite3 firstmed_demo.db
```

### Step 2: Verify Current Migration State

Run this query to see what migrations Alembic thinks are applied:

**PostgreSQL/SQLite:**
```sql
SELECT version_num, is_primary FROM alembic_version ORDER BY version_num;
```

**Expected output (if migrations ran but failed on 0013):**
```
version_num | is_primary
-----------+-----------
0001        | t
0002        | t
0003        | t
...
0012        | t
```

If `0013` or `0014` appear, they failed to complete due to the broken revision ID.

---

## Fix Options

### Option A: Mark 0013 & 0014 as Already Applied (Recommended)

This tells Alembic "these migrations have been dealt with — skip them."

**PostgreSQL:**
```sql
-- Insert the fixed revision IDs so Alembic knows they're complete
INSERT INTO alembic_version (version_num, is_primary) 
VALUES ('0013', true)
ON CONFLICT (version_num) DO NOTHING;

INSERT INTO alembic_version (version_num, is_primary) 
VALUES ('0014', true)
ON CONFLICT (version_num) DO NOTHING;

-- Verify
SELECT version_num, is_primary FROM alembic_version ORDER BY version_num;
```

**SQLite:**
```sql
-- Insert the fixed revision IDs
INSERT OR IGNORE INTO alembic_version (version_num, is_primary) 
VALUES ('0013', 1);

INSERT OR IGNORE INTO alembic_version (version_num, is_primary) 
VALUES ('0014', 1);

-- Verify
SELECT version_num, is_primary FROM alembic_version ORDER BY version_num;
```

---

### Option B: Clean Slate (If Migrations Are Truly Broken)

If the migrations ran partially and left the database in an inconsistent state:

**PostgreSQL:**
```sql
-- Remove all migration records (starts fresh)
DELETE FROM alembic_version;

-- The next deployment will run all migrations from scratch
-- This is safe if you're OK with data loss (use only for development/staging)
```

**Then:**
1. Rebuild the Docker image with the fixed migrations
2. Deploy — Alembic will run 0001 through 0014 in sequence
3. All migrations should succeed with the fixed revision IDs

---

### Option C: Manually Apply Migration 0013 & 0014 SQL

If you want to apply the actual schema changes without waiting for the Docker container:

#### Migration 0013: Create `connected_accounts` table

**PostgreSQL:**
```sql
-- Create the new connected_accounts table
CREATE TABLE IF NOT EXISTS connected_accounts (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    provider_type VARCHAR(20) NOT NULL,
    provider_email VARCHAR(320) NOT NULL,
    provider_sub VARCHAR(255),
    access_token_enc TEXT,
    refresh_token_enc TEXT,
    token_expiry TIMESTAMP WITH TIME ZONE,
    scopes TEXT NOT NULL DEFAULT '',
    history_id VARCHAR(64),
    imap_host VARCHAR(255),
    imap_port INTEGER,
    smtp_host VARCHAR(255),
    smtp_port INTEGER,
    imap_username VARCHAR(320),
    imap_password_enc TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_connected_accounts PRIMARY KEY (id),
    CONSTRAINT uq_connected_accounts_user_id UNIQUE (user_id),
    CONSTRAINT fk_connected_accounts_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Index for lookups
CREATE INDEX IF NOT EXISTS ix_connected_accounts_user_id ON connected_accounts(user_id);

-- Migrate existing Gmail credentials if google_credentials table exists
INSERT INTO connected_accounts
    (id, user_id, provider_type, provider_email, provider_sub,
     access_token_enc, refresh_token_enc, token_expiry,
     scopes, history_id, created_at, updated_at)
SELECT
    id,
    user_id,
    'gmail' AS provider_type,
    google_email AS provider_email,
    google_sub AS provider_sub,
    access_token_enc,
    refresh_token_enc,
    token_expiry,
    scopes,
    history_id,
    created_at,
    updated_at
FROM google_credentials
ON CONFLICT (user_id) DO NOTHING;

-- Rename draft_reviews columns (requires batch mode in production)
-- This is complex due to constraints; safer to let Alembic handle it

-- Mark migration 0013 as applied
INSERT INTO alembic_version (version_num, is_primary) 
VALUES ('0013', true)
ON CONFLICT (version_num) DO NOTHING;
```

#### Migration 0014: Drop `google_credentials` table

**PostgreSQL:**
```sql
-- Only run AFTER 0013 is complete and data is in connected_accounts
DROP TABLE IF EXISTS google_credentials CASCADE;

-- Mark migration 0014 as applied
INSERT INTO alembic_version (version_num, is_primary) 
VALUES ('0014', true)
ON CONFLICT (version_num) DO NOTHING;
```

---

## Recommended Deployment Path

### For Development (SQLite)
1. Stop the container
2. Delete the SQLite database file: `rm backend/firstmed_demo.db`
3. Rebuild the Docker image: `docker-compose build`
4. Start the container: `docker-compose up`
5. Alembic will run all migrations from scratch with the fixed revision IDs

### For Staging/Production (PostgreSQL)

**Quick fix (if migrations failed):**
```bash
# Connect to your database
psql postgresql://user:pass@host:5432/dbname

# Run Option A (mark migrations complete):
INSERT INTO alembic_version (version_num, is_primary) 
VALUES ('0013', true), ('0014', true)
ON CONFLICT (version_num) DO NOTHING;
```

**Then redeploy:**
```bash
# Rebuild image with fixed migrations
docker-compose build

# Deploy (Alembic will skip 0013/0014 since they're marked complete)
docker-compose up
```

**Full reset (if needed):**
```bash
# Connect to database
psql postgresql://user:pass@host:5432/dbname

# Clear migration history
DELETE FROM alembic_version;

# Exit psql
\q

# Rebuild and deploy
docker-compose build && docker-compose up
```

---

## How to Verify Success

After deployment, check:

1. **Container logs show successful migration:**
   ```bash
   docker logs firstmed-backend 2>&1 | grep alembic
   ```
   Should show:
   ```
   INFO  [alembic.runtime.migration] Running upgrade 0013 -> 0014, Drop google_credentials table
   INFO  [alembic.runtime.migration] Done.
   ```

2. **Backend health check passes:**
   ```bash
   curl http://localhost:8000/health
   ```
   Should return: `{"status": "ok"}`

3. **Database shows all migrations:**
   ```sql
   SELECT version_num FROM alembic_version ORDER BY version_num;
   ```
   Should show `0001` through `0014`

---

## Troubleshooting

### "Error: constraint "..." does not exist"
- This means migrations partially ran. Use **Option B (Clean Slate)** — delete the database and redeploy.

### "duplicate key value violates unique constraint"
- Something is trying to apply migrations twice. Check that you've only inserted `0013` and `0014` once in the alembic_version table.

### "relation does not exist" on draft_reviews columns
- If renaming columns failed, you'll need to manually apply the column renames. This is complex — use the clean slate approach instead.

### Container still crashing after marking migrations complete
- The stale Docker image still has broken migration files. **You must rebuild the image** to pick up the fixed migrations from your codebase.
  ```bash
  docker-compose build --no-cache
  docker-compose up
  ```

---

## Summary

| Scenario | Action |
|----------|--------|
| Development/SQLite | Delete DB file, rebuild image, redeploy |
| Staging/Production, migrations partially failed | Use Option A (mark complete), rebuild image, redeploy |
| Staging/Production, need full reset | Use Option B (clean slate), rebuild image, redeploy |
| Want to manually apply schema changes | Use Option C (manual SQL), then mark complete |

**All scenarios require: Rebuild Docker image to get the fixed migration files from your updated codebase.**
