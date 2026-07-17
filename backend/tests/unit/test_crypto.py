"""Unit tests for the Fernet token-encryption helpers."""

from __future__ import annotations

import pytest
from app.core import crypto


def test_round_trip():
    ciphertext = crypto.encrypt("refresh-token-value")
    assert ciphertext != "refresh-token-value"
    assert crypto.decrypt(ciphertext) == "refresh-token-value"


def test_distinct_ciphertexts_for_same_plaintext():
    # Fernet embeds a random IV/timestamp, so two encryptions differ.
    assert crypto.encrypt("x") != crypto.encrypt("x")


def test_decrypt_rejects_garbage():
    with pytest.raises(crypto.InvalidToken):
        crypto.decrypt("not-a-valid-fernet-token")
