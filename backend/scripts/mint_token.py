"""Mint an app JWT for a user by email (dev/testing only).

SSO-provisioned users have no password, so this is the way to get a bearer token
for API calls without going through the browser OAuth redirect.

    cd backend && python scripts/mint_token.py [email]
"""

from __future__ import annotations

import asyncio
import sys

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token
from app.repositories.user import UserRepository

DEFAULT_EMAIL = "abdulmoeedqureshi4@gmail.com"


async def main() -> None:
    email = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EMAIL
    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_email(email)
        if user is None:
            print(f"No user found for {email}", file=sys.stderr)
            raise SystemExit(1)
        token = create_access_token(str(user.id), extra_claims={"role": user.role.value})
        print(token)


if __name__ == "__main__":
    asyncio.run(main())
