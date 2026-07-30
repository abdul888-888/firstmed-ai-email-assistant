"""Ad-hoc test: exercise the Sync Inbox path (POST /api/v1/workflows/pull).

Mints a JWT for each active user (same call the Google-callback uses) and hits
the real HTTP endpoint the frontend button calls, so this covers auth dep +
endpoint + WorkflowService + Gmail + AI end-to-end.
"""

import asyncio
import json
import urllib.error
import urllib.request

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token
from app.repositories.user import UserRepository

BASE = "http://localhost:8000/api/v1"


def call_pull(token: str, max_results: int = 3):
    req = urllib.request.Request(
        f"{BASE}/workflows/pull?max_results={max_results}",
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:  # noqa: BLE001
        return None, repr(e)


async def main():
    print("ai_configured:", settings.ai_configured)
    print("google_oauth_configured:", settings.google_oauth_configured)
    print("-" * 60)

    async with AsyncSessionLocal() as session:
        users = await UserRepository(session).list_active()

    if not users:
        print("NO ACTIVE USERS. Sign in via Google first.")
        return

    for u in users:
        has_creds = bool(getattr(u, "google_credentials", None) or getattr(u, "gmail_credentials", None))
        print(f"user={u.email} id={u.id} role={u.role} google_connected={has_creds}")
        token = create_access_token(str(u.id), extra_claims={"role": u.role.value})
        status, body = call_pull(token)
        try:
            body = json.dumps(json.loads(body), indent=2)
        except Exception:  # noqa: BLE001
            pass
        print(f"  -> HTTP {status}")
        for line in str(body).splitlines():
            print(f"     {line}")
        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
