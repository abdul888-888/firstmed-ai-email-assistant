"""Portable vector column type.

``PortableVector`` is a native ``pgvector`` ``Vector(dim)`` column on PostgreSQL
(enabling the ``<=>`` ANN distance operator), and a plain JSON array everywhere
else (SQLite, used by the test suite, has no vector extension).
"""

from __future__ import annotations

from typing import Any

from pgvector.sqlalchemy import Vector as PGVector
from sqlalchemy import JSON
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


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
