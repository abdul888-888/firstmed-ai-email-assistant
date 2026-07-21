# Token Status Checker Guide

## Your Token Status

**Token Expiration:** 60 minutes from login time
**Current Configuration:** `access_token_expire_minutes: 60` (in `backend/app/core/config.py`)

## How to Check Your Token Status

### Method 1: Use the New Token Status Page (Recommended)

Navigate to: `http://localhost:3000/token-status`

This page provides:
- ✅ Real-time token status (updates every second)
- ✅ Exact expiration time
- ✅ Time remaining countdown
- ✅ User ID and role
- ✅ Visual status indicator (green = valid, yellow = expiring soon, red = expired)
- ✅ One-click refresh or sign out buttons

### Method 2: Browser Console Check

Open your browser's Developer Tools (F12) and run:

```javascript
// Check if you have a token
const token = localStorage.getItem('firstmed_access_token');
console.log('Has token:', !!token);

// Decode and check expiration
function checkToken(token) {
  if (!token) {
    console.log('❌ No token found');
    return;
  }

  const parts = token.split('.');
  if (parts.length !== 3) {
    console.log('❌ Invalid token format');
    return;
  }

  try {
    const payload = JSON.parse(
      atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'))
    );
    
    const expiresAt = new Date(payload.exp * 1000);
    const now = new Date();
    const isExpired = now > expiresAt;
    const minutesLeft = Math.floor((expiresAt - now) / 60000);

    console.log('✅ Token found');
    console.log('User ID (sub):', payload.sub);
    console.log('Role:', payload.role);
    console.log('Expires at:', expiresAt.toLocaleString());
    console.log('Minutes remaining:', minutesLeft);
    console.log('Status:', isExpired ? '❌ EXPIRED' : '✅ VALID');
  } catch (error) {
    console.error('Failed to decode token:', error);
  }
}

// Run it
checkToken(token);
```

### Method 3: API Health Check

Make a request to your current user endpoint:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  http://localhost:8000/api/v1/auth/me
```

**Response if token is valid:**
```json
{
  "id": "...",
  "email": "user@example.com",
  "full_name": "...",
  "role": "admin",
  "is_active": true
}
```

**Response if token is expired:**
```json
{
  "detail": "Invalid authentication credentials"
}
(Status: 401 Unauthorized)
```

## Token Expiration Timeline

| Time | Status | Action |
|------|--------|--------|
| 0 min | Token issued | You just signed in ✅ |
| 5 min | Valid | Still plenty of time ✅ |
| 30 min | Valid | Halfway through ✅ |
| 55 min | Expiring soon | ⚠️ Consider refreshing soon |
| 59 min | About to expire | ⚠️ Status page shows red |
| 60 min | EXPIRED | ❌ Must sign in again |
| 61 min | EXPIRED | ❌ All API calls return 401 |

## Understanding Token Components

A JWT token has 3 parts separated by dots:

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.
eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.
SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
```

- **Part 1 (Header):** Algorithm and token type
- **Part 2 (Payload):** Claims including `exp` (expiration timestamp) and `sub` (user ID)
- **Part 3 (Signature):** HMAC signature for verification

The `exp` claim is a Unix timestamp (seconds since Jan 1, 1970).

## Token Fields in Payload

```json
{
  "sub": "uuid-of-user",           // Subject (user ID)
  "iat": 1721621234,               // Issued at (timestamp)
  "exp": 1721624834,               // Expires at (timestamp)
  "type": "access",                // Token type
  "jti": "unique-id-string",       // JWT ID (unique identifier)
  "role": "admin"                  // User role (from extra_claims)
}
```

## What Happens When Token Expires

1. **Frontend:** Any API call returns `401 Unauthorized`
2. **User sees:** "Invalid authentication credentials" error
3. **Action required:** Click "Sign In Again" button or navigate to `/auth/google/login`
4. **Process:** Complete Google OAuth flow again
5. **Result:** New token issued, valid for 60 more minutes

## Extending Token Lifetime

**To change the token expiration time:**

Edit `backend/app/core/config.py`:

```python
access_token_expire_minutes: int = 120  # Change from 60 to 120 minutes
```

Then restart the backend server.

**Note:** Only affects NEW tokens issued after the change. Existing tokens keep their original expiration.

## Security Considerations

✅ **Why short expiration (60 min)?**
- Limits damage if token is stolen
- Requires regular re-authentication
- Sessions don't get stale

✅ **Token Storage:**
- Stored in browser's `localStorage`
- Never sent to servers in cookies (uses header instead)
- Cleared on browser exit (user's choice)

✅ **Best Practices:**
- Don't share your token with anyone
- Clear your token if you suspect it was compromised
- Sign out when done with the application
- Use HTTPS in production (tokens can be intercepted over HTTP)

## Troubleshooting

### "Token Expired" but I just signed in?

**Cause:** Server clock is out of sync with client clock
**Solution:** Sync your computer's system time

### Token status page shows "About to expire" but I just signed in?

**Cause:** 
- Client clock ahead of server
- Or token has been active for 55+ minutes

**Solution:** Sign in again or check your computer's time

### Can't decode token in console?

**Cause:** Invalid token format or token has been modified
**Solution:** Sign in again to get a fresh token

### API keeps returning 401 even with token?

**Cause:** 
- Token is expired
- Token is malformed
- Backend secret key changed

**Solution:** Sign in again

## Implementation Details

### Frontend Token Checker (`frontend/lib/token-status.ts`)

```typescript
function checkTokenStatus(token: string | null): TokenStatus {
  // Returns: {
  //   hasToken: boolean
  //   isExpired: boolean
  //   expiresAt: Date | null
  //   expiresIn: number | null (seconds)
  //   userInfo: { sub, role } | null
  // }
}
```

### Backend Token Creation (`backend/app/core/security.py`)

```python
def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    now = dt.datetime.now(dt.UTC)
    expire = now + dt.timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": expire,
        "type": "access",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
```

## Token Lifecycle Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ USER SIGNS IN (Google OAuth)                                │
├─────────────────────────────────────────────────────────────┤
│ 1. User clicks "Sign In"                                    │
│ 2. Backend creates JWT token with exp = now + 60 minutes    │
│ 3. Frontend stores in localStorage                          │
│ 4. API calls include: Authorization: Bearer <token>         │
└─────────────────────────────────────────────────────────────┘
                        ⬇ (0-59 minutes)
┌─────────────────────────────────────────────────────────────┐
│ TOKEN IS VALID                                              │
├─────────────────────────────────────────────────────────────┤
│ ✅ All API requests succeed (200-status responses)          │
│ ✅ User can access protected routes                         │
│ ✅ Backend verifies token on every request                  │
└─────────────────────────────────────────────────────────────┘
                        ⬇ (59-60 minutes)
┌─────────────────────────────────────────────────────────────┐
│ TOKEN EXPIRES                                               │
├─────────────────────────────────────────────────────────────┤
│ ❌ API requests return 401 Unauthorized                     │
│ ❌ User is redirected to sign in page                       │
│ ❌ localStorage still has token (but invalid)               │
└─────────────────────────────────────────────────────────────┘
                        ⬇ (user action)
┌─────────────────────────────────────────────────────────────┐
│ USER SIGNS IN AGAIN                                         │
├─────────────────────────────────────────────────────────────┤
│ 1. New JWT token is created (with fresh expiration)         │
│ 2. Old token in localStorage is replaced                    │
│ 3. API calls resume successfully                            │
└─────────────────────────────────────────────────────────────┘
```

## Testing Token Expiration

To test expiration behavior:

1. Sign in normally
2. Note the expiration time from the status page
3. Wait until expiration or adjust your system clock
4. Try to make an API call (e.g., navigate to `/reviews`)
5. Observe the 401 error and sign-in redirect
6. Sign in again
7. Verify it works and token is refreshed

---

**Page Location:** `http://localhost:3000/token-status`
**Last Updated:** 2026-07-21
