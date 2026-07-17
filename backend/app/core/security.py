"""Security primitives: password hashing (bcrypt) and JWT access tokens.

Shared by both local email/password auth and the Google SSO flow (Phase 2),
which reuses :func:`create_access_token` to issue the same bearer JWT.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

# bcrypt hashes at most 72 bytes of input; longer inputs must be truncated.
_BCRYPT_MAX_BYTES = 72


def _truncate(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Return a salted bcrypt hash for ``password``."""
    return bcrypt.hashpw(_truncate(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Constant-time check of ``password`` against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(_truncate(password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str,
    *,
    expires_minutes: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT access token for ``subject`` (typically a user id)."""
    now = dt.datetime.now(dt.UTC)
    expire = now + dt.timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": expire,
        "type": "access",
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises ``jwt.PyJWTError`` on failure."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
