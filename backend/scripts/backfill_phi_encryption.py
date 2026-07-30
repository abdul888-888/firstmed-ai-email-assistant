"""One-time backfill: encrypt pre-existing plaintext PHI columns.

``DraftReview.subject`` / ``draft_body`` / ``summary`` / ``specialist_input``
switched from plain ``Text`` to ``EncryptedText`` (see
``app/models/types.py``). The column TYPE in the database didn't change (it's
still ``TEXT``) so no schema migration is needed — but any row written
*before* this change is still sitting there as plaintext, and the ORM will now
try (and fail) to Fernet-decrypt it on read.

Run this once, after deploying the encryption change and setting
``PHI_ENCRYPTION_KEY``, against any database that has pre-existing rows (a
fresh/empty database needs no backfill at all). Idempotent and safe to re-run:
each value is decrypt-tested first, so already-encrypted rows (including ones
partially migrated by an earlier interrupted run) are left untouched.

    cd backend && .venv/Scripts/python.exe scripts/backfill_phi_encryption.py

See docs/security/phi-encryption-and-anthropic-baa.md for the full rollout
checklist.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.core import crypto
from app.core.config import settings
from app.core.crypto import InvalidToken
from app.core.database import AsyncSessionLocal

_FIELDS = ("subject", "draft_body", "summary", "specialist_input")


def _reencrypt_if_plaintext(value: str | None) -> tuple[str | None, bool]:
    """Return ``(value_to_store, changed)``.

    ``None`` passes through untouched (never encrypted, see ``EncryptedText``).
    Anything else is decrypt-tested: success means it's already ciphertext
    (leave alone); ``InvalidToken`` means legacy plaintext (encrypt it now).
    """
    if value is None:
        return None, False
    try:
        crypto.decrypt_phi(value)
        return value, False
    except InvalidToken:
        return crypto.encrypt_phi(value), True


async def main() -> None:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(f"SELECT id, {', '.join(_FIELDS)} FROM draft_reviews")
            )
        ).all()

        migrated = 0
        for row in rows:
            row_id = row[0]
            values = dict(zip(_FIELDS, row[1:], strict=True))
            new_values: dict[str, str | None] = {}
            changed = False
            for field, value in values.items():
                new_value, field_changed = _reencrypt_if_plaintext(value)
                new_values[field] = new_value
                changed = changed or field_changed
            if not changed:
                continue
            set_clause = ", ".join(f"{f} = :{f}" for f in _FIELDS)
            await session.execute(
                text(f"UPDATE draft_reviews SET {set_clause} WHERE id = :id"),
                {**new_values, "id": row_id},
            )
            migrated += 1

        await session.commit()

    print(f"DB: {settings.sqlalchemy_database_uri}")
    print(f"Scanned {len(rows)} draft_reviews row(s); encrypted {migrated} with legacy plaintext.")


if __name__ == "__main__":
    asyncio.run(main())
