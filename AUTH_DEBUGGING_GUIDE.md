# 401 Unauthorized - Debugging & Fix Guide

## Problem
Frontend is getting `401 Unauthorized` errors when making authenticated API requests to the backend (e.g., `GET /api/v1/reviews/pending`).

---

## Step 1: Verify Environment Configuration

### Frontend
✅ **Create/update `.env.local` in the frontend directory:**
```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Then restart the dev server:
```bash
cd frontend
npm run dev
```

### Backend
✅ **Verify `.env` file in backend directory has:**
```
SECRET_KEY=8c8l7j2kP1O5Zeq8-Pshg8lmEcqhpFCUNqlc7AUkPYAzknVeAPZ-QnNrSErDJF1s
ALGORITHM=HS256
GOOGLE_CLIENT_ID="your_google_client_id_here"
GOOGLE_CLIENT_SECRET="your_google_client_secret_here"
```

---

## Step 2: Diagnose the Issue

### 2.1 Check if Token is Being Stored

1. Open your browser (with frontend running at `http://localhost:3000`)
2. Go through the sign-in flow with Google
3. After successful sign-in, open **DevTools** → **Console**
4. Run this command:
   ```javascript
   localStorage.getItem('firstmed_access_token')
   ```

**Expected Result:**
- Should show a long JWT token (starts with `eyJ...`)
- If it shows `null`, the token is NOT being stored

**If NULL - Fix:**
- Check browser console for errors during auth callback
- Verify the auth callback page is working: navigate to `http://localhost:3000/auth/callback`
- Check if `setToken()` is being called in the callback page

### 2.2 Check if Auth Header is Being Sent

1. In browser DevTools → **Network tab**
2. Make a request to `/reviews` or `/analytics`
3. Click on the request
4. Go to **Request Headers** section
5. Look for: `Authorization: Bearer eyJ...`

**Expected Result:**
- Should see `Authorization: Bearer {token}` in the request headers

**If Missing - Fix:**
Update `frontend/lib/auth.ts` to ensure `authHeader()` is being called:
```typescript
export function authHeader(): Record<string, string> {
  const token = getToken();
  console.log("Auth header check:", { hasToken: !!token });
  return token ? { Authorization: `Bearer ${token}` } : {};
}
```

Then check browser console to confirm `hasToken: true`.

---

## Step 3: Test Backend Token Validation

### 3.1 Manual Token Test

Open a terminal and run:

```bash
# 1. Get the token from browser console and save it
TOKEN="<paste_token_here>"

# 2. Test the health endpoint (no auth needed)
curl http://localhost:8000/api/v1/health

# 3. Test with the token
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/reviews/pending
```

**Expected Results:**
- Health endpoint: `{"status": "ok"}`
- Reviews endpoint with token: Should return reviews list (not 401)

**If 401 with token:**
- Token might be invalid or expired
- Backend SECRET_KEY might not match what token was signed with
- See "Step 4: Verify Token Signing" below

### 3.2 Backend Auth Debug

Add this to `backend/app/api/deps.py` temporarily for debugging:

```python
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated user from a bearer token."""
    print(f"DEBUG: Received token: {token[:50]}...")  # Print first 50 chars
    print(f"DEBUG: SECRET_KEY: {settings.secret_key.get_secret_value()[:20]}...")
    
    try:
        payload = decode_access_token(token)
        print(f"DEBUG: Decoded payload: {payload}")
        # ... rest of code
```

Then check the backend console output when making an authenticated request.

---

## Step 4: Verify Token Signing (Backend Secret Key)

### Critical Issue: Secret Key Mismatch

If the **same token** that **worked yesterday** now fails, the backend's `SECRET_KEY` may have changed.

**Check:**
```bash
cd backend
grep SECRET_KEY .env
```

**Backend must be restarted after `.env` changes:**
```bash
# Kill the backend process
# Then restart:
cd backend
source .venv/Scripts/activate  # or .venv\Scripts\activate on Windows
uvicorn app.main:app --reload
```

---

## Step 5: Frontend API Request Configuration

Verify that `frontend/app/reviews/page.tsx` (and other pages) are using `authHeader()`:

**Current (should be correct):**
```typescript
async function api(path: string, init?: RequestInit) {
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: { 
      "Content-Type": "application/json", 
      ...authHeader(),  // ✅ This adds Authorization header
      ...(init?.headers ?? {}) 
    },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail ?? `Request failed (${res.status})`);
  return data;
}
```

**If not present, add it:**
```typescript
import { authHeader, getToken } from "@/lib/auth";

// Then ensure it's in the headers of every fetch call
headers: { 
  "Content-Type": "application/json",
  ...authHeader(),  // ← Add this line
  ...(init?.headers ?? {})
}
```

---

## Step 6: CORS & Credentials Configuration

### Backend CORS (should be fine)
In `backend/app/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,  # includes http://localhost:3000
    allow_credentials=True,  # ✅ Required for Bearer tokens
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Frontend Fetch Credentials
For complex CORS scenarios, add credentials to fetch:

```typescript
async function api(path: string, init?: RequestInit) {
  const res = await fetch(`${base}${path}`, {
    ...init,
    credentials: 'include',  // ← Add this if token is in cookies
    headers: { 
      "Content-Type": "application/json",
      ...authHeader(),
      ...(init?.headers ?? {}) 
    },
  });
  // ...
}
```

**Note:** Currently the frontend stores token in **localStorage**, not cookies, so `credentials: 'include'` may not be necessary. But it doesn't hurt.

---

## Step 7: Quick Diagnostic Commands

### Frontend Debug

In browser console:
```javascript
// Check token storage
console.log("Token:", localStorage.getItem('firstmed_access_token')?.substring(0, 50) + "...");

// Test actual fetch
fetch('http://localhost:8000/api/v1/reviews/pending', {
  headers: {
    'Authorization': `Bearer ${localStorage.getItem('firstmed_access_token')}`,
    'Content-Type': 'application/json'
  }
}).then(r => {
  console.log('Status:', r.status);
  return r.json();
}).then(d => console.log('Response:', d))
.catch(e => console.error('Error:', e));
```

### Backend Debug

```bash
# Check if backend is running
curl http://localhost:8000/api/v1/health

# Check backend logs for auth errors
# (should be visible in the terminal where you ran `uvicorn`)
```

---

## Step 8: Full E2E Test Flow

1. **Clear browser storage:**
   ```javascript
   localStorage.clear();
   location.reload();
   ```

2. **Sign in again** with Google

3. **Check token stored:**
   ```javascript
   localStorage.getItem('firstmed_access_token') // Should NOT be null
   ```

4. **Navigate to `/reviews`**
   - Should load without 401 error
   - Should show the dashboard with live status indicator

5. **Check Network tab** for the request:
   - Request should have `Authorization: Bearer ...` header
   - Response should be `200 OK` with reviews data, not `401`

---

## Checklist for Full Resolution

- [ ] `.env.local` created in frontend with `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`
- [ ] Frontend dev server restarted after env change
- [ ] Backend still running (port 8000)
- [ ] Backend `.env` has correct `SECRET_KEY`
- [ ] Backend restarted after any `.env` changes
- [ ] Browser localStorage has token after sign-in
- [ ] Network requests include `Authorization: Bearer ...` header
- [ ] `/reviews` loads without 401 error

---

## Common Causes & Solutions

| Issue | Cause | Fix |
|-------|-------|-----|
| Token is `null` after sign-in | Auth callback not parsing fragment | Check browser console for errors on `/auth/callback` page |
| Token exists but still 401 | Token not in request headers | Verify `authHeader()` is being called in fetch |
| Works once, then 401 | Token expired (default 60 min) | Request new token by signing out and back in |
| Always 401 even with valid token | Backend SECRET_KEY changed | Restart backend after `.env` changes |
| 401 on `/reviews` but 200 on `/health` | Auth dependency not called for that endpoint | Endpoint might need `Depends(get_current_user)` |
| CORS error before 401 | `allow_origins` wrong | Verify `http://localhost:3000` in backend CORS config |

---

## If Still Stuck

1. **Add debug logging** to both frontend and backend
2. **Check browser DevTools** → Network → request headers and response
3. **Check backend console** for validation errors
4. **Restart both** frontend and backend fresh:
   ```bash
   # Terminal 1: Kill all Node processes
   taskkill /IM node.exe /F
   
   # Terminal 2: Kill all Python processes (if backend is running)
   taskkill /IM python.exe /F
   
   # Terminal 1: Restart frontend
   cd frontend && npm run dev
   
   # Terminal 2: Restart backend
   cd backend && source .venv/Scripts/activate && uvicorn app.main:app --reload
   ```

5. **Check backend `/docs`** (Swagger UI):
   - Visit `http://localhost:8000/docs`
   - Try the "Authorize" button with your token
   - Should work without 401

