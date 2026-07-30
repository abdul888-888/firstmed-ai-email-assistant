#!/usr/bin/env python
"""Check authentication setup: users in DB, SECRET_KEY, token validation."""

import asyncio
import sys
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.repositories.user import UserRepository
from app.core.security import decode_access_token
import jwt

async def main():
    print("\n" + "="*60)
    print("🔍 AUTHENTICATION DIAGNOSTIC")
    print("="*60 + "\n")

    # Check 1: Configuration
    print("1️⃣  CONFIGURATION")
    print("-" * 60)
    secret_key = settings.secret_key.get_secret_value()
    print(f"✅ SECRET_KEY length: {len(secret_key)} chars")
    print(f"   First 20 chars: {secret_key[:20]}...")
    print(f"✅ Algorithm: {settings.algorithm}")
    print(f"✅ Access token expires: {settings.access_token_expire_minutes} minutes")
    print(f"✅ Google OAuth configured: {settings.google_oauth_configured}")
    print()

    # Check 2: Database users
    print("2️⃣  DATABASE USERS")
    print("-" * 60)
    try:
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            users = await repo.list_active()

            if not users:
                print("❌ NO USERS FOUND IN DATABASE")
                print("\n   This is the problem! When you sign in with Google,")
                print("   the backend should create a user record.")
                print("\n   You haven't completed Google OAuth sign-in yet.")
                print("   Go to: http://localhost:3000")
                print("   Click: 'Sign in with Google'")
                print("   Then run this script again.")
            else:
                print(f"✅ Found {len(users)} user(s):\n")
                for user in users:
                    print(f"   Email: {user.email}")
                    print(f"   ID: {user.id}")
                    print(f"   Active: {user.is_active}")
                    print(f"   Role: {user.role}")
                    print()
    except Exception as e:
        print(f"❌ Error reading database: {e}")
        return False
    print()

    # Check 3: Token validation test
    if users:
        print("3️⃣  TOKEN VALIDATION TEST")
        print("-" * 60)

        # Create a test token
        from app.core.security import create_access_token
        test_token = create_access_token(str(users[0].id), extra_claims={"role": users[0].role.value})

        print(f"Created test token for user: {users[0].email}")
        print(f"Token (first 50 chars): {test_token[:50]}...\n")

        try:
            decoded = decode_access_token(test_token)
            print(f"✅ Token decoded successfully!")
            print(f"   Subject (user ID): {decoded.get('sub')}")
            print(f"   Type: {decoded.get('type')}")
            print(f"   Expires: {decoded.get('exp')}")
            print()
            print("✅ Backend CAN validate tokens with current SECRET_KEY")
        except jwt.PyJWTError as e:
            print(f"❌ Token validation failed: {e}")
            print("\n   This means the backend can't decode tokens.")
            print("   Likely cause: SECRET_KEY changed after token was issued.")
            return False
    else:
        print("3️⃣  TOKEN VALIDATION TEST")
        print("-" * 60)
        print("⏭️  Skipped (no users in database yet)")
        print("   Sign in with Google first, then run this script again.")
        print()

    print("="*60)
    print("SUMMARY")
    print("="*60)
    if not users:
        print("""
❌ NO USERS IN DATABASE

This is why you're getting 401:
1. You haven't completed Google OAuth sign-in
2. No user record was created in the database
3. Backend can't find the user for the token

FIX:
1. Go to: http://localhost:3000
2. Click: "Sign in with Google"
3. Complete Google authentication
4. Run this script again
""")
    else:
        print("""
✅ USERS FOUND & TOKENS VALIDATE

If you're still getting 401:
1. Try signing out and back in
2. Check browser console for token details
3. Run: http://localhost:3000/test-auth
4. Check backend console (Terminal 2) for errors
""")
    print("="*60 + "\n")

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result is not False else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
