"""Phase 14: Specialist collaboration + irrelevant email handling.

Adds specialist input mechanism for escalated emails and irrelevant status.

Revision ID: 0002
Revises: 0001_initial
Create Date: 2026-07-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add specialist collaboration columns
    op.add_column(
        "draft_reviews",
        sa.Column("specialist_input", sa.Text(), nullable=True),
    )
    op.add_column(
        "draft_reviews",
        sa.Column("specialist_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "draft_reviews",
        sa.Column("specialist_input_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("draft_reviews", "specialist_input_at")
    op.drop_column("draft_reviews", "specialist_id")
    op.drop_column("draft_reviews", "specialist_input")
