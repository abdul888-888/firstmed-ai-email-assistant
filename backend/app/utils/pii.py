"""PII masking helpers.

Used by logging (and, in later phases, by anything that persists or exports
free-text) to keep patient-identifying data out of logs, per the PRD's GDPR /
"PII masking in logs" requirement.
"""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# Phone-like runs of 7+ digits, tolerating spaces / dashes / parens / plus.
_PHONE_RE = re.compile(r"(?<!\d)(\+?[\d][\d\s().-]{6,}\d)(?!\d)")


def mask_email(value: str) -> str:
    """Mask the local part of an email: ``jane.doe@x.com`` -> ``j***@x.com``."""

    def _repl(match: re.Match[str]) -> str:
        local, _, domain = match.group(0).partition("@")
        head = local[0] if local else ""
        return f"{head}***@{domain}"

    return _EMAIL_RE.sub(_repl, value)


def mask_phone(value: str) -> str:
    """Mask long digit runs that look like phone numbers."""

    def _repl(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) < 7:
            return match.group(0)
        return "***" + digits[-2:]

    return _PHONE_RE.sub(_repl, value)


def mask_pii(value: str) -> str:
    """Apply all PII masks to a string."""
    if not value:
        return value
    return mask_phone(mask_email(value))
