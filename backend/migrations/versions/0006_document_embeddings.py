"""semantic retrieval: document embeddings

Revision ID: 0006_document_embeddings
Revises: 0005_review_actions
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_document_embeddings"
down_revision: str | None = "0005_review_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("embedding", sa.JSON(), nullable=True))
    op.add_column(
        "documents", sa.Column("embedding_model", sa.String(length=128), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("documents", "embedding_model")
    op.drop_column("documents", "embedding")
