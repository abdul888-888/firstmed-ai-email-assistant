"""workflow engine: draft_reviews

Revision ID: 0004_draft_reviews
Revises: 0003_documents
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_draft_reviews"
down_revision: str | None = "0003_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "draft_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=128), nullable=False),
        sa.Column("gmail_thread_id", sa.String(length=128), nullable=False),
        sa.Column("message_id_header", sa.Text(), nullable=False),
        sa.Column("sender", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=32), nullable=False),
        sa.Column("urgency", sa.String(length=32), nullable=False),
        sa.Column("department", sa.String(length=32), nullable=False),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("draft_body", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("gmail_draft_id", sa.String(length=128), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_draft_reviews_user_id"), "draft_reviews", ["user_id"])
    op.create_index(op.f("ix_draft_reviews_status"), "draft_reviews", ["status"])
    op.create_index("ix_draft_reviews_user_status", "draft_reviews", ["user_id", "status"])
    op.create_index("ix_draft_reviews_gmail_message_id", "draft_reviews", ["gmail_message_id"])


def downgrade() -> None:
    op.drop_index("ix_draft_reviews_gmail_message_id", table_name="draft_reviews")
    op.drop_index("ix_draft_reviews_user_status", table_name="draft_reviews")
    op.drop_index(op.f("ix_draft_reviews_status"), table_name="draft_reviews")
    op.drop_index(op.f("ix_draft_reviews_user_id"), table_name="draft_reviews")
    op.drop_table("draft_reviews")
