# Quick Fix: One-Liner Commands to Fix Alembic Migrations

## TL;DR
Your backend is crashing because migrations 0013/0014 have broken revision IDs in the old Docker image. The fix is to mark them as "already applied" in the database, then rebuild the Docker image.

---

## Choose Your Environment

### Local Development (SQLite)

**Fastest option - start fresh:**
```bash
# Stop and remove containers
docker-compose down

# Delete the SQLite database (contains stale migration markers)
rm backend/firstmed_demo.db

# Rebuild with fixed migrations and start
docker-compose build --no-cache
docker-compose up
```

---

### Docker Compose (PostgreSQL - Staging)

**Step 1: Mark migrations as complete**
```bash
docker exec firstmed-db psql -U firstmed -d firstmed -c \
  "INSERT INTO alembic_version (version_num, is_primary) VALUES ('0013', true), ('0014', true) ON CONFLICT (version_num) DO NOTHING;"
```

**Step 2: Rebuild image and redeploy**
```bash
docker-compose build --no-cache
docker-compose up
```

---

### Docker Compose Staging (PostgreSQL)

**Step 1: Mark migrations as complete**
```bash
docker exec firstmed-postgres-staging psql -U firstmed_user -d firstmed_staging -c \
  "INSERT INTO alembic_version (version_num, is_primary) VALUES ('0013', true), ('0014', true) ON CONFLICT (version_num) DO NOTHING;"
```

**Step 2: Rebuild and redeploy**
```bash
docker-compose -f docker-compose.staging.yml build --no-cache
docker-compose -f docker-compose.staging.yml up
```

---

### Railway (Production/Staging - PostgreSQL)

**Step 1: Get your database credentials**
- Go to Railway dashboard → Your project → Database service
- Copy the connection URL

**Step 2: Connect and mark migrations**
```bash
# Replace with your actual connection string
psql "postgresql://user:password@host:5432/dbname" -c \
  "INSERT INTO alembic_version (version_num, is_primary) VALUES ('0013', true), ('0014', true) ON CONFLICT (version_num) DO NOTHING;"
```

**Step 3: Redeploy (trigger rebuild)**
```bash
# Push a code change to trigger rebuild, or use Railway CLI
railway deploy
```

**Or manually via Railway UI:**
- Go to your project's API service
- Click "Deploy" button to trigger a rebuild with the fixed migration files

---

### Manual SQL for Any PostgreSQL Database

```sql
-- Mark migrations 0013 and 0014 as complete
INSERT INTO alembic_version (version_num, is_primary) 
VALUES 
    ('0013', true),
    ('0014', true)
ON CONFLICT (version_num) DO NOTHING;

-- Verify it worked
SELECT version_num FROM alembic_version ORDER BY version_num;
```

Run via:
- **psql:** `psql -U user -d dbname < fix_migrations.sql`
- **PgAdmin:** Copy/paste into query window
- **DBeaver:** Copy/paste into query editor

---

### Manual SQL for SQLite Database

```sql
INSERT OR IGNORE INTO alembic_version (version_num, is_primary) 
VALUES 
    ('0013', 1),
    ('0014', 1);

SELECT version_num FROM alembic_version ORDER BY version_num;
```

Run via:
```bash
sqlite3 firstmed_demo.db < fix_migrations.sql
```

---

## Verify It Worked

After running your fix command, check:

### 1. Database has the migrations marked
```bash
# PostgreSQL
psql -U user -d dbname -c "SELECT version_num FROM alembic_version WHERE version_num IN ('0013', '0014');"

# SQLite
sqlite3 firstmed_demo.db "SELECT version_num FROM alembic_version WHERE version_num IN ('0013', '0014');"
```

You should see:
```
version_num
-----------
0013
0014
```

### 2. Rebuild Docker image with fixed migrations
```bash
docker-compose build --no-cache
```

### 3. Check container starts successfully
```bash
docker-compose up
```

Container logs should show:
```
INFO  [alembic.runtime.migration] Running upgrade 0013 -> 0014
INFO  [alembic.runtime.migration] Done.
INFO  [uvicorn.server] Started server process
```

### 4. Test the API
```bash
curl http://localhost:8000/health
```

Should return: `{"status":"ok"}`

---

## If Something Goes Wrong

### "relation alembic_version does not exist"
- Alembic hasn't been initialized yet
- Start the container once; it will create the table automatically

### "duplicate key value violates"
- Migrations were already partially applied
- See "Clean Slate Option" in ALEMBIC_MIGRATION_RECOVERY.md

### Container still crashes after these steps
- The old Docker image is still cached
- Run: `docker-compose build --no-cache --pull`
- This forces Docker to rebuild from scratch with the fixed migration files

### "KeyError: '0013'" still appears
- The container is still using the old image
- Verify the image was rebuilt: `docker images | grep firstmed`
- Check image creation date — should be recent
- If old: `docker rmi firstmed-api` then `docker-compose build`

---

## What This Actually Does

| Step | Action | Why |
|------|--------|-----|
| Mark 0013/0014 complete | Insert into alembic_version table | Tells Alembic "these migrations have been applied" |
| Rebuild Docker image | `docker-compose build --no-cache` | Picks up fixed migration files from your code (old image had broken ones) |
| Redeploy | `docker-compose up` | New image starts, Alembic skips 0013/0014 (marked complete), proceeds to next migrations |

The **fixed migration files already exist** in your repository. The old Docker image couldn't parse them because the revision IDs were broken. This fix bridges the gap until the new image builds.

---

## Need More Details?

See `ALEMBIC_MIGRATION_RECOVERY.md` for:
- Detailed explanation of what went wrong
- Manual SQL to apply migrations without Alembic
- Clean slate option (start fresh)
- Troubleshooting guide
