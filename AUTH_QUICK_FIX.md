# ⚡ Quick Fix: 401 Unauthorized Errors

## Problem
API calls return `401 Unauthorized` when trying to access `/api/v1/reviews/pending` and other authenticated endpoints.

## Quick Diagnostic (5 minutes)

### Step 1: Check Environment Setup
```bash
# Make sure frontend .env.local exists
cat frontend/.env.local
# Should output: NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

If missing, create it:
```bash
echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000" > frontend/.env.local
```

### Step 2: Restart Frontend
```bash
cd frontend
npm run dev
# Wait for "Ready in X.Xs"
```

### Step 3: Run Diagnostic Dashboard
1. Open browser: `http://localhost:3000/debug`
2. Click **"Run Tests"** button
3. Check results:
   - ✅ All green = authentication working
   - ❌ Red items = needs fixing

### Step 4: Interpret Results

| Result | Meaning | Fix |
|--------|---------|-----|
| "Token in localStorage" = ❌ | Not signed in | Go to home page, click "Sign in with Google" |
| "Token in localStorage" = ✅ but "Authenticated Request" = ❌ 401 | Token invalid | Sign out and back in |
| "Backend Health" = ❌ | Backend not running | Restart backend (see below) |
| All ✅ | Perfect! Issue resolved | N/A |

---

## If Diagnostic Shows "Backend Health = ❌"

### Make sure backend is running:
```bash
# Terminal 1: Kill old process
taskkill /IM python.exe /F

# Terminal 2: Start backend
cd backend
source .venv/Scripts/activate  # On Windows: .venv\Scripts\activate
uvicorn app.main:app --reload
# Wait for: "Uvicorn running on http://0.0.0.0:8000"
```

### Verify it's working:
```bash
curl http://localhost:8000/api/v1/health
# Should return: {"status":"ok"}
```

---

## If Diagnostic Shows Token But Still 401

### Common cause: Backend restarted and SECRET_KEY changed

**Check backend `.env`:**
```bash
cd backend
cat .env | grep SECRET_KEY
# Should show the long secret key
```

**Then restart backend:**
```bash
# Kill any running backend process
taskkill /IM python.exe /F

# Restart it
cd backend
source .venv/Scripts/activate
uvicorn app.main:app --reload
```

**Then sign out and back in:**
1. Browser: `http://localhost:3000`
2. Click profile → "Sign Out"
3. Sign in with Google again
4. Go to `/debug` and run tests again

---

## If Still Stuck

### Full Nuclear Option (Start from scratch)

```bash
# Kill all processes
taskkill /IM node.exe /F
taskkill /IM python.exe /F

# Clear browser data
# Go to Chrome DevTools → Application → LocalStorage → Delete all

# Restart frontend
cd frontend
npm run dev

# In a new terminal, restart backend
cd backend
source .venv/Scripts/activate
uvicorn app.main:app --reload

# In browser, clear cache and sign in fresh
# Ctrl+Shift+Delete to open Clear Browsing Data
# Check "Cookies and other site data" and "Cached images and files"
# Click Clear Data

# Then navigate to http://localhost:3000 and sign in
```

### Check Debug Page
1. Go to `http://localhost:3000/debug`
2. Click "Run Tests"
3. Screenshot the results
4. Post to your team or check `AUTH_DEBUGGING_GUIDE.md` for detailed troubleshooting

---

## Expected Flow After Fix

1. ✅ Navigate to `http://localhost:3000`
2. ✅ Click "Sign in with Google"
3. ✅ Authenticate with Google account
4. ✅ Redirected to `/reviews` (Inbox Queue)
5. ✅ See:
   - "Live Monitoring Active" indicator (green pulsing dot)
   - Three metric cards (Awaiting Action, Approved Threads, Uptime)
   - List of pending emails to review
6. ✅ Click an email item to see draft reply
7. ✅ Click "Approve & Send Outbound" button (emerald green)
8. ✅ Status changes to "Approved"

If all of this works, **authentication is fixed!** 🎉

---

## Verify Each Component

### Frontend Sending Token?
```javascript
// In browser console:
fetch('http://localhost:8000/api/v1/reviews/pending', {
  headers: {
    'Authorization': `Bearer ${localStorage.getItem('firstmed_access_token')}`,
    'Content-Type': 'application/json'
  }
}).then(r => console.log('Status:', r.status)).catch(e => console.error(e))
```

Should print: `Status: 200` (not 401)

### Backend Receiving Token?
Check the backend console/logs for validation logs.

Add this temporarily to `backend/app/api/deps.py`:
```python
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    print(f"DEBUG: Token received: {token[:50]}...")
    # ... rest of code
```

If you see the debug output, the token is being sent. If not, frontend isn't sending it.

---

## Prevention Checklist

- [ ] `.env.local` exists in frontend with correct API URL
- [ ] Frontend dev server restarted after `.env.local` changes
- [ ] Backend `.env` has consistent `SECRET_KEY` (never changes)
- [ ] Backend restarted whenever `.env` changes
- [ ] Both frontend and backend running on correct ports (3000 & 8000)
- [ ] Google OAuth configured in backend `.env`

---

## Need More Help?

Read the detailed guide: `AUTH_DEBUGGING_GUIDE.md`

Key sections:
- **Step 2**: Verify Token Storage (is localStorage populated?)
- **Step 3**: Check Headers (are we sending the auth header?)
- **Step 4**: Verify Token Signing (is the SECRET_KEY consistent?)
