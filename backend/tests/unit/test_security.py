"""Unit tests for password hashing and JWT tokens."""

from __future__ import annotations

import jwt
import pytest
from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password_roundtrip():
    hashed = hash_password("s3cret-password")
    assert hashed != "s3cret-password"
    assert verify_password("s3cret-password", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("correct-horse")
    assert verify_password("wrong-password", hashed) is False


def test_verify_password_handles_garbage_hash():
    assert verify_password("anything", "not-a-real-hash") is False


def test_long_password_is_accepted():
    # bcrypt truncates at 72 bytes; a longer password must not raise.
    long_password = "x" * 200
    hashed = hash_password(long_password)
    assert verify_password(long_password, hashed) is True


def test_access_token_roundtrip():
    token = create_access_token("user-123", extra_claims={"role": "admin"})
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_expired_token_is_rejected():
    token = create_access_token("user-123", expires_minutes=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_token_with_wrong_signature_is_rejected():
    token = create_access_token("user-123")
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "different-secret", algorithms=[settings.algorithm])
