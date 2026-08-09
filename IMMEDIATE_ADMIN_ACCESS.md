# Immediate Admin Access Workaround

## Root Cause Identified
The frontend at `https://firstmed-ai-email-assistant.vercel.app` is configured to call `localhost:8000` instead of the Railway API `https://api-production-c575.up.railway.app`.

## Quick Access Method

### Step 1: Get Valid JWT Token
Run this in PowerShell to get a valid admin token:
```powershell
$body = @{username='bscs24140@itu.edu.pk'; password='ITU@888888'}
$response = Invoke-RestMethod -Uri "https://api-production-c575.up.railway.app/api/v1/auth/login" -Method POST -Body $body -ContentType "application/x-www-form-urlencoded"
Write-Host "Token: $($response.access_token)"
```

### Step 2: Manually Set Token in Browser
1. Go to: `https://firstmed-ai-email-assistant.vercel.app/admin`
2. Open browser DevTools (F12) → Console
3. Run this JavaScript:
```javascript
localStorage.setItem('auth_token', 'PASTE_TOKEN_HERE');
// Then refresh the page
location.reload();
```

### Step 3: Alternative - Direct API Access
You can test all admin functionality directly via API:
```powershell
$token = "PASTE_TOKEN_HERE"
$headers = @{Authorization = "Bearer $token"}

# List users
Invoke-RestMethod -Uri "https://api-production-c575.up.railway.app/api/v1/admin/users" -Headers $headers

# Other admin endpoints...
```

## Current API Response (Working)
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "requires_2fa": false,
  "challenge_id": null,
  "role": "ADMIN", 
  "redirect_url": "/admin"
}
```

## Next Steps for Permanent Fix
1. Configure Vercel environment variables through dashboard
2. Set `NEXT_PUBLIC_API_BASE_URL=https://api-production-c575.up.railway.app`
3. Redeploy frontend
4. Test complete login flow