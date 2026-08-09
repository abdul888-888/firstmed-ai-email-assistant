-- ============================================================================
-- ALEMBIC MIGRATION FIX - QUICK SCRIPT
-- ============================================================================
--
-- This script marks migrations 0013 and 0014 as complete in the database,
-- allowing Alembic to skip them on the next deployment.
--
-- USAGE:
-- 
-- PostgreSQL:
--   psql -U username -d dbname < fix_migrations.sql
--
-- SQLite:
--   sqlite3 dbname.db < fix_migrations.sql
--
-- Docker Compose (PostgreSQL):
--   docker exec firstmed-db psql -U firstmed -d firstmed < fix_migrations.sql
--
-- Railway (psql client required):
--   psql postgresql://user:pass@host:5432/dbname < fix_migrations.sql
--
-- ============================================================================

-- Step 1: Check current migration state
-- If you don't see this output, something is wrong
SELECT 
    'Current Alembic Version History' AS info,
    version_num,
    is_primary
FROM alembic_version 
ORDER BY version_num;

-- Step 2: Mark migrations 0013 and 0014 as complete
-- This tells Alembic they've been applied, so it won't try to run them again
INSERT INTO alembic_version (version_num, is_primary) 
VALUES 
    ('0013', true),
    ('0014', true)
ON CONFLICT (version_num) DO NOTHING;

-- Step 3: Verify the fix worked
SELECT 
    'After Fix - Alembic Version History' AS info,
    version_num,
    is_primary
FROM alembic_version 
ORDER BY version_num;

-- Step 4: Expected result
-- You should now see 0013 and 0014 in the list
-- 
-- If yes: ✅ SUCCESS
--   - Rebuild your Docker image: docker-compose build --no-cache
--   - Redeploy: docker-compose up
--   - Container should now start without KeyError: '0013'
--
-- If you got duplicate key errors:
--   - 0013 and 0014 were already partially applied
--   - See ALEMBIC_MIGRATION_RECOVERY.md for clean-slate option
