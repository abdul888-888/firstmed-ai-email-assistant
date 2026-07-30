# 🔧 Fix: Authenticated Request 401 (Token Validation Issue)

## What's Happening
✅ Token exists  
✅ Auth header is being sent  
❌ Backend is rejecting it with 401

**This means the backend can't validate your token.**

---

## Quickest Fix (Try This First)

### Option 1: Sign Out and Back In (60 seconds)
This gets a fresh token that matches the current backend SECRET_KEY:

1. **In browser**, go to `http://localhost:3000`
2. **Open DevTools** → Console
3. **Clear localStorage:**
   ```javascript
   localStorage.clear()
   ```
4. **Sign out** (if you see a sign-out button anywhere)
5. **Refresh page**: `http://localhost:3000`
6. **Sign in with Google** again
7. **Go to `/debug`** and run tests again

**Why this works**: Gets a new token signed with the current backend SECRET_KEY

---

## If That Didn't Work

### Check Backend SECRET_KEY (Most Common Issue)

The backend signs tokens with a SECRET_KEY. If it changes, old tokens become invalid.

**Step 1: Check the backend SECRET_KEY**
```bash
cd backend
cat .env | findstr SECRET_KEY
```

Should output something like:
```
SECRET_KEY=8c8l7j2kP1O5Zeq8-Pshg8lmEcqhpFCUNqlc7AUkPYAzknVeAPZ-QnNrSErDJF1s
```

**Step 2: Verify it's the same every time**
Run the command again. If it's different, your `.env` is corrupted.

**Step 3: If SECRET_KEY looks correct**
Restart the backend to ensure it's using this key:

```bash
# Kill the backend
taskkill /IM python.exe /F

# Wait 2 seconds

# Restart it
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload
```

Then clear browser cache and sign in again (Option 1 above).

---

## Debug the Exact Error

### Step 1: Check Backend Console
Look at **Terminal 2** where backend is running. You should see error logs like:

**Good log** (token is being processed):
```
INFO:     GET /api/v1/reviews/pending HTTP/1.1" 200
```

**Bad log** (token validation failed):
```
DEBUG: Token received: eyJhbGc...
ERROR: jwt.InvalidSignatureError
```

If you see **signature error**, the backend can't verify your token signature. This means the SECRET_KEY used to sign the token doesn't match the current backend SECRET_KEY.

**Fix**: 
1. Verify `.env` SECRET_KEY hasn't changed
2. Restart backend
3. Sign in again

---

### Step 2: Check If User Exists in Database

Sometimes the token is valid, but the user doesn't exist. Verify:

```bash
# In backend directory
.venv\Scripts\activate
python -c "
import asyncio
from app.core.database import AsyncSessionLocal
from app.repositories.user import UserRepository

async def check():
    async with AsyncSessionLocal() as session:
        users = await UserRepository(session).list_all()
        for u in users:
            print(f'User: {u.email} (ID: {u.id}, Active: {u.is_active})')

asyncio.run(check())
"
```

Should show at least one user (your Google email).

If **no users** are shown:
- You haven't completed Google OAuth yet
- Or the database is empty

**Fix**: Sign in with Google again at `http://localhost:3000`

---

## Manual Token Test

Get your actual token and test it directly:

### Step 1: Get the Token
In browser console:
```javascript
localStorage.getItem('firstmed_access_token')
```

Copy the entire token (it's a long string starting with `eyJ`).

### Step 2: Test with curl
```bash
# Replace TOKEN with the actual token from above
curl -H "Authorization: Bearer TOKEN_HERE" \
     http://localhost:8000/api/v1/reviews/pending
```

**If you get 401:**
- Token is invalid
- Backend can't verify it
- Try: Sign out → clear localStorage → sign in again

**If you get 200 with data:**
- The token works!
- But frontend isn't sending it properly
- Try: Restart frontend

---

## Nuclear Option: Reset Everything

If nothing above works:

```bash
# Kill all processes
taskkill /IM node.exe /F
taskkill /IM python.exe /F

# Clear browser data
# Chrome DevTools: Ctrl+Shift+Delete
# Check: Cookies, cached data, localStorage
# Click: Clear data

# Delete database to start fresh
cd backend
rm firstmed_demo.db

# Wait 5 seconds

# Restart frontend (Terminal 1)
cd frontend
npm run dev

# Restart backend (Terminal 2)
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload

# In browser: http://localhost:3000
# Sign in with Google again
# Go to /debug and test
```

---

## Verify Backend is Actually Receiving the Token

Add temporary debug logging:

**File**: `backend/app/api/deps.py`

Find this function:
```python
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
```

Add debug lines at the top:
```python
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    print(f"[DEBUG] Token received (first 50 chars): {token[:50] if token else 'NONE'}")
    print(f"[DEBUG] SECRET_KEY being used: {settings.secret_key.get_secret_value()[:20]}...")
    
    try:
        payload = decode_access_token(token)
        print(f"[DEBUG] Token decoded successfully. User ID: {payload.get('sub')}")
```

Restart backend:
```bash
taskkill /IM python.exe /F
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload
```

Now go to `/debug` and run tests. Check Terminal 2 for the debug output:

**If you see**:
- `Token received (first 50 chars): eyJhbGc...` → Token IS being sent ✅
- `Token decoded successfully. User ID: ...` → Token IS valid ✅
- Then the issue might be in the database or user lookup

**If you see**:
- `Token received: NONE` → Frontend not sending it ❌
- `jwt.InvalidSignatureError` → Secret key mismatch ❌

---

## The Real Issue - 99% of the Time

Backend is rejecting because:

1. **Token was signed with OLD SECRET_KEY**
   - Backend restarted
   - `.env` was changed
   - **Fix**: Sign in again to get new token

2. **Token is malformed or corrupted**
   - Might be cut off in localStorage
   - **Fix**: Clear localStorage, sign in again

3. **Backend and frontend have different SECRET_KEYS**
   - Extremely rare
   - **Fix**: Check `.env` is the same, restart backend

---

## Checklist to Try (In Order)

1. [ ] Sign out → Clear localStorage → Sign in again (Option 1 above)
2. [ ] Restart backend (`taskkill /IM python.exe /F`, restart)
3. [ ] Check `.env` SECRET_KEY hasn't changed
4. [ ] Verify user exists in database (Step 2 of manual test)
5. [ ] Add debug logging (see above) and check backend console
6. [ ] Try manual curl test with actual token
7. [ ] Full nuclear reset (all processes, clear DB, restart)

---

## Still Stuck?

If after all this `/debug` still shows 401 on the authenticated request:

**Check these files:**
- Backend `.env` - Do you have correct `SECRET_KEY` and `GOOGLE_*` settings?
- Backend logs - What's the exact error message?
- Database - Did you seed demo data? (`python scripts/seed_demo.py`)

**Run this to check setup:**
```bash
cd backend
python -c "from app.core.config import settings; print(f'SECRET_KEY: {settings.secret_key.get_secret_value()[:20]}...'); print(f'Google configured: {settings.google_oauth_configured}')"
```

Should show:
- ✅ A long SECRET_KEY
- ✅ `Google configured: True`

If Google is False, update `.env` with `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

