# Database Migration Fix Summary

## Problem
When deploying with the new Claude API key, the backend crashed with:
```
KeyError: '0013'
Revision 0013 referenced from 0013 -> 0014 (head), 
Drop google_credentials table (Phase 5 cleanup). is not present
```

## Root Cause
Alembic (the database migration tool) manages migrations using a revision chain. Each migration has:
- A `revision` ID (what it's called)
- A `down_revision` ID (what migration it depends on)

The problem was **mismatched revision IDs**:

| File | Had | Should Be |
|------|-----|-----------|
| `0010_unique_gmail_message.py` | `revision = "0010_unique_gmail_message"` | `revision = "0010"` |
| `0011_specialist_input.py` | `revision = "0011_specialist_input"` | `revision = "0011"` |
| `0012_gmail_history_id.py` | `revision = "0012_gmail_history_id"` | `revision = "0012"` |
| `0013_connected_accounts.py` | `revision = "0013_connected_accounts"` | `revision = "0013"` |
| `0014_drop_google_credentials.py` | `down_revision = "0013"` | ✅ Correct (after 0013 fix) |

Additionally, all `down_revision` references had the same issue - they used long names instead of simple numbers.

## Solution Applied
Fixed all revision IDs in these files:
1. **backend/migrations/versions/0010_unique_gmail_message.py**
   - `revision: "0010_unique_gmail_message"` → `"0010"`
   - `down_revision: "0009_collaboration"` → `"0009"`

2. **backend/migrations/versions/0011_specialist_input.py**
   - `revision: "0011_specialist_input"` → `"0011"`
   - `down_revision: "0010_unique_gmail_message"` → `"0010"`

3. **backend/migrations/versions/0012_gmail_history_id.py**
   - `revision: "0012_gmail_history_id"` → `"0012"`
   - `down_revision: "0011_specialist_input"` → `"0011"`

4. **backend/migrations/versions/0013_connected_accounts.py**
   - `revision: "0013_connected_accounts"` → `"0013"`
   - `down_revision: "0012_gmail_history_id"` → `"0012"`

5. **backend/migrations/versions/0014_drop_google_credentials.py**
   - `down_revision: "0013"` → `"0013"` ✅ (already correct, just updated docstring)

## Why This Happened
The migration files were created with descriptive names (good for documentation), but Alembic's revision chain expects **simple numeric IDs** for parsing and chaining. The longer names broke the chain because Alembic couldn't find `"0013"` when looking for it - it only existed as `"0013_connected_accounts"`.

## How to Deploy Now
1. **Stop your running containers**
2. **Pull the latest code** with these migration fixes
3. **Restart the backend** - Alembic will now successfully migrate:
   ```bash
   alembic upgrade head
   ```

The migration will proceed through:
- 0010 → 0011 → 0012 → 0013 → 0014 (head)

## Verification
After deployment, you should see:
```
INFO  [alembic.runtime.migration] Running upgrade 0013 -> 0014, Drop google_credentials table (Phase 5 cleanup).
```

No more `KeyError: '0013'` errors.

## Files Modified
- `backend/migrations/versions/0010_unique_gmail_message.py`
- `backend/migrations/versions/0011_specialist_input.py`
- `backend/migrations/versions/0012_gmail_history_id.py`
- `backend/migrations/versions/0013_connected_accounts.py`
- `backend/migrations/versions/0014_drop_google_credentials.py` (docstring only)

## Next Steps
1. Re-deploy the backend with these migration fixes
2. Claude API integration should now work properly (it was never the problem - just timing)
3. All drafts should generate with high confidence scores
