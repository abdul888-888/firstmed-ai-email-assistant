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


# --- PHI encryption (dedicated key, independent from the token key) --------


def test_phi_round_trip():
    ciphertext = crypto.encrypt_phi("Patient asks about refill.")
    assert ciphertext != "Patient asks about refill."
    assert crypto.decrypt_phi(ciphertext) == "Patient asks about refill."


def test_phi_decrypt_rejects_garbage():
    with pytest.raises(crypto.InvalidToken):
        crypto.decrypt_phi("not-a-valid-fernet-token")


def test_phi_key_differs_from_token_key_in_dev_fallback():
    # Both keys derive from the same SECRET_KEY when unset — the PHI
    # derivation must be salted differently so a token ciphertext never
    # decrypts under the PHI key or vice versa.
    token_ciphertext = crypto.encrypt("shared-plaintext")
    phi_ciphertext = crypto.encrypt_phi("shared-plaintext")
    with pytest.raises(crypto.InvalidToken):
        crypto.decrypt_phi(token_ciphertext)
    with pytest.raises(crypto.InvalidToken):
        crypto.decrypt(phi_ciphertext)
