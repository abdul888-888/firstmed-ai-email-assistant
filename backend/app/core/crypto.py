"""Symmetric encryption for secrets at rest (OAuth tokens, PHI columns).

Uses Fernet (AES-128-CBC + HMAC). Two independent keys are used, each with its
own dev-only derived fallback so a developer's local secret never
accidentally collides between the two purposes:

- ``settings.token_encryption_key`` (``TOKEN_ENCRYPTION_KEY``) — OAuth tokens.
- ``settings.phi_encryption_key`` (``PHI_ENCRYPTION_KEY``) — patient-identifying
  review content (see ``app.models.types.EncryptedText``).

Production MUST set both explicitly (generate with
``python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"``)
so encrypted data survives a ``SECRET_KEY`` rotation and the two purposes can
be rotated independently — see ``docs/security/phi-encryption-and-anthropic-baa.md``.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

__all__ = ["encrypt", "decrypt", "encrypt_phi", "decrypt_phi", "InvalidToken"]


def _derive_key_from_secret(secret: str, *, purpose: str = "") -> bytes:
    """Derive a valid 32-byte urlsafe-base64 Fernet key from an arbitrary secret.

    ``purpose`` salts the derivation so different dev-fallback keys (token vs.
    PHI) never collide even when both are derived from the same
    ``SECRET_KEY``. Omitted entirely for the token key so existing encrypted
    OAuth tokens keep decrypting unchanged.
    """
    material = f"{purpose}:{secret}" if purpose else secret
    digest = hashlib.sha256(material.encode("utf-8")).digest()
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


@lru_cache
def _phi_fernet() -> Fernet:
    key = settings.phi_encryption_key.get_secret_value().strip()
    key_bytes = (
        key.encode("utf-8")
        if key
        else _derive_key_from_secret(settings.secret_key.get_secret_value(), purpose="phi")
    )
    return Fernet(key_bytes)


def encrypt(plaintext: str) -> str:
    """Encrypt a UTF-8 string with the OAuth-token key, returning a urlsafe token."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    """Decrypt a token produced by :func:`encrypt`. Raises ``InvalidToken``."""
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")


def encrypt_phi(plaintext: str) -> str:
    """Encrypt a UTF-8 string with the dedicated PHI key, returning a urlsafe token."""
    return _phi_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_phi(token: str) -> str:
    """Decrypt a token produced by :func:`encrypt_phi`. Raises ``InvalidToken``."""
    return _phi_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
