"""internal collaboration: review assignment + notes

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("draft_reviews", sa.Column("assigned_to", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_draft_reviews_assigned_to"), "draft_reviews", ["assigned_to"])
    op.create_foreign_key(
        "fk_draft_reviews_assigned_to_users",
        "draft_reviews",
        "users",
        ["assigned_to"],
        ["id"],
    )

    op.create_table(
        "review_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(["review_id"], ["draft_reviews.id"]),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_review_notes_review_id"), "review_notes", ["review_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_review_notes_review_id"), table_name="review_notes")
    op.drop_table("review_notes")
    op.drop_constraint("fk_draft_reviews_assigned_to_users", "draft_reviews", type_="foreignkey")
    op.drop_index(op.f("ix_draft_reviews_assigned_to"), table_name="draft_reviews")
    op.drop_column("draft_reviews", "assigned_to")
