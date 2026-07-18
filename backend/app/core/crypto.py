"""Symmetric encryption for secrets at rest (OAuth tokens).

Uses Fernet (AES-128-CBC + HMAC). The key comes from
``settings.token_encryption_key`` when set; otherwise a deterministic key is
derived from ``settings.secret_key`` so development works out of the box.

Production MUST set an explicit ``TOKEN_ENCRYPTION_KEY`` (generate with
``python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"``)
so tokens survive a ``SECRET_KEY`` rotation and aren't tied to the JWT secret.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

__all__ = ["encrypt", "decrypt", "InvalidToken"]


def _derive_key_from_secret(secret: str) -> bytes:
    """Derive a valid 32-byte urlsafe-base64 Fernet key from an arbitrary secret."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache
def _fernet() -> Fernet:
    key = settings.token_encryption_key.get_secret_value().strip()
    key_bytes = (
        key.encode("utf-8")
        if key
        else _derive_key_from_secret(settings.secret_key.get_secret_value())
    )
    return Fernet(key_bytes)


def encrypt(plaintext: str) -> str:
    """Encrypt a UTF-8 string, returning a urlsafe token string."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    """Decrypt a token produced by :func:`encrypt`. Raises ``InvalidToken``."""
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
