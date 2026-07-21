# Google Sign-In Debugging Guide

## Issue Fixed ✅

**Problem:** Frontend running on port 3003, but backend configured for port 3000
**Solution:** Updated `.env` with correct ports and CORS configuration

---

## Configuration Changes Made

### 1. Updated `.env` file:
```bash
FRONTEND_BASE_URL=http://localhost:3003
BACKEND_CORS_ORIGINS=http://localhost:3000 http://localhost:3002 http://localhost:3003
```

### 2. What these changes do:
- **FRONTEND_BASE_URL:** Where users are redirected after OAuth success
- **BACKEND_CORS_ORIGINS:** Allow requests from these frontend URLs
- Both now support ports 3000, 3002, and 3003 for development flexibility

---

## Step-by-Step Testing

### Step 1: Verify Backend Configuration
```bash
curl http://localhost:8000/api/v1/auth/google/login
```

Expected response: JSON with `authorization_url` containing:
- ✅ `client_id`: Your Google OAuth client ID
- ✅ `redirect_uri`: `http://localhost:8000/api/v1/auth/google/callback`
- ✅ Requested scopes: openid, email, profile, gmail.readonly, gmail.compose

### Step 2: Test the Sign-In Button
1. Open http://localhost:3003
2. Click "**Sign in with Google**"
3. You should be redirected to Google's consent screen
4. After granting permissions, you'll be redirected back to `/auth/callback`

### Step 3: Check Token was Set
After redirect, open browser DevTools (F12) and check:
```javascript
localStorage.getItem('firstmed_access_token')
```

Should return a long JWT token, not `null`.

### Step 4: Verify Token Status
Navigate to: http://localhost:3003/token-status

Should show:
- ✅ "Token Valid" (green badge)
- ✅ Your User ID
- ✅ Your Role
- ✅ Expiration time

---

## Troubleshooting

### "Sign in failed" error

**Check 1: Is backend running?**
```bash
curl http://localhost:8000/api/v1/health
```
Should return: `{"status":"ok",...}`

**Check 2: Is frontend reaching backend?**
Open DevTools Console (F12) and run:
```javascript
fetch('http://localhost:8000/api/v1/auth/google/login')
  .then(r => r.json())
  .then(d => console.log(d))
```

Should show authorization_url, not an error.

### "Redirect URI mismatch" error in Google consent screen

**Cause:** Google Cloud Console settings don't match backend config
**Fix:** Update Google Cloud Console:
1. Go to https://console.cloud.google.com/
2. Find your project
3. Go to OAuth 2.0 Credentials
4. Edit your OAuth app
5. Set Authorized redirect URIs to:
   - `http://localhost:8000/api/v1/auth/google/callback`

### Token not appearing in localStorage

**Check 1:** Are you being redirected to `/auth/callback`?
- Browser URL should be: `http://localhost:3003/auth/callback#access_token=...`

**Check 2:** Is there an error in the URL?
- URL might contain: `#error=access_denied`
- This means you denied permissions in Google consent screen

**Check 3:** Check browser console for errors
- Open DevTools → Console tab
- Look for any error messages
- Check Network tab to see if `/auth/callback` request succeeded

### "Invalid authentication credentials" when accessing API

**Cause:** Token exists but is invalid
**Fix:**
1. Clear localStorage: `localStorage.clear()`
2. Sign in again
3. Get fresh token

---

## How Google OAuth Flow Works

```
1. User clicks "Sign in with Google"
2. Frontend asks backend: "Give me Google consent URL"
3. Backend returns URL to Google's consent screen
4. Frontend redirects browser to Google
5. User grants permissions on Google consent screen
6. Google redirects back to: http://localhost:8000/api/v1/auth/google/callback?code=...
7. Backend exchanges code for tokens
8. Backend creates JWT token
9. Backend redirects to: http://localhost:3003/auth/callback#access_token=...
10. Frontend parses token from URL fragment
11. Frontend stores token in localStorage
12. Frontend redirects to /reviews dashboard
```

### Key: URL Fragment vs Query Params

- **Code from Google:** Sent as query param `?code=...` (sent to backend)
- **Token to Frontend:** Sent as fragment `#access_token=...` (never sent to server)
- This keeps tokens out of server logs and only in browser memory

---

## Port Configuration Reference

| Port | Service | Purpose |
|------|---------|---------|
| 8000 | Backend | FastAPI server + OAuth callback endpoint |
| 3003 | Frontend | Next.js dev server (might be 3002 or 3000) |

All CORS origins updated to support all three ports.

---

## Quick Test Commands

**Verify backend health:**
```bash
curl http://localhost:8000/api/v1/health
```

**Get OAuth URL:**
```bash
curl http://localhost:8000/api/v1/auth/google/login | grep authorization_url
```

**Check current token:**
```bash
# In browser console:
localStorage.getItem('firstmed_access_token')
```

**Verify token validity:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/auth/me
```

Should return your user info (200 status)

---

## Debugging Checklist

- [ ] Backend is running on port 8000
- [ ] Frontend is running on port 3003
- [ ] `.env` file updated with correct FRONTEND_BASE_URL and BACKEND_CORS_ORIGINS
- [ ] Backend restarted after .env changes
- [ ] Google Client ID and Secret are in `.env`
- [ ] Google Cloud Console has correct redirect URI
- [ ] No CORS errors in browser console
- [ ] Token appears in localStorage after callback
- [ ] Token shows as valid in `/token-status` page

---

## Testing OAuth Scopes

Your app requests these permissions from Google:
1. **openid** - Get unique user ID
2. **email** - Get user's email address
3. **profile** - Get user's name and photo
4. **gmail.readonly** - Read emails from shared inbox
5. **gmail.compose** - Create and send draft emails

All are required for the full feature set.

---

## Getting Help

1. **Check backend logs:** `tail -f /tmp/backend.log`
2. **Check frontend logs:** `tail -f /tmp/frontend.log`
3. **Browser DevTools:** F12 → Console and Network tabs
4. **Token Status Page:** http://localhost:3003/token-status

---

**Last Updated:** 2026-07-21
**Configuration:** Updated for port 3003
