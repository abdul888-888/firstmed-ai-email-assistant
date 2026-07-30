"""Portable vector column type + transparent field-level encryption.

``PortableVector`` is a native ``pgvector`` ``Vector(dim)`` column on PostgreSQL
(enabling the ``<=>`` ANN distance operator), and a plain JSON array everywhere
else (SQLite, used by the test suite, has no vector extension).

``EncryptedText`` transparently encrypts patient-identifying text columns at
rest (Fernet, ``PHI_ENCRYPTION_KEY`` — see ``app.core.crypto``). Application
code (repositories, services, Pydantic schemas) always sees plaintext; only
the bytes actually written to the database are ciphertext. The underlying
column type is still ``TEXT`` (``impl = Text``), so switching a column to
``EncryptedText`` needs no DDL migration — only a one-time data backfill for
any pre-existing plaintext rows (see ``scripts/backfill_phi_encryption.py``).
"""

from __future__ import annotations

from typing import Any

from pgvector.sqlalchemy import Vector as PGVector
from sqlalchemy import JSON, Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.core import crypto


class PortableVector(TypeDecorator):
    """Vector(dim) on PostgreSQL, JSON array on other dialects."""

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.dim = dim

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGVector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        return list(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        return list(value)


class EncryptedText(TypeDecorator):
    """A ``Text`` column encrypted at rest with the PHI key (Fernet).

    ``NULL`` passes through unchanged (no ciphertext for absent data); an
    empty string is still encrypted, so its stored bytes don't visibly signal
    "empty" to anyone with raw DB access.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        return crypto.encrypt_phi(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        return crypto.decrypt_phi(value)
