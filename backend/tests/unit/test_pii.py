"""Unit tests for PII masking."""

from __future__ import annotations

from app.utils.pii import mask_email, mask_phone, mask_pii


def test_mask_email():
    assert mask_email("jane.doe@example.com") == "j***@example.com"


def test_mask_email_within_text():
    masked = mask_email("contact patient@clinic.org please")
    assert "patient@clinic.org" not in masked
    assert "@clinic.org" in masked


def test_mask_phone():
    masked = mask_phone("call +1 (555) 123-4567 now")
    assert "555" not in masked
    assert masked.endswith("67 now")


def test_mask_pii_combined():
    masked = mask_pii("email a@b.com or phone 5551234567")
    assert "a@b.com" not in masked
    assert "5551234567" not in masked


def test_mask_pii_empty():
    assert mask_pii("") == ""
