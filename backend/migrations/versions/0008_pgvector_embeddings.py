"""pgvector embeddings

Revision ID: 0008_pgvector_embeddings
Revises: 0007_templates
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.core.config import settings
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "ix_documents_embedding_cosine"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite (tests) has no vector extension; the JSON column from 0006
        # already serves as the portable fallback (see app/models/types.py).
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # JSON -> vector can't be cast automatically; existing rows are dropped and
    # re-populated by the embedding backfill (documents with a null embedding
    # are treated as needing re-embedding).
    op.alter_column(
        "documents",
        "embedding",
        type_=Vector(settings.embedding_dim),
        postgresql_using="NULL",
    )
    op.create_index(
        _INDEX_NAME,
        "documents",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index(_INDEX_NAME, table_name="documents")
    op.alter_column(
        "documents",
        "embedding",
        type_=sa.JSON(),
        postgresql_using="NULL",
    )
