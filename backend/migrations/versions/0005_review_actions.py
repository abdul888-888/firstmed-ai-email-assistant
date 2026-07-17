"""review actions: reject note + send tracking

Revision ID: 0005_review_actions
Revises: 0004_draft_reviews
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_review_actions"
down_revision: str | None = "0004_draft_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("draft_reviews", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column(
        "draft_reviews", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "draft_reviews", sa.Column("sent_message_id", sa.String(length=128), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("draft_reviews", "sent_message_id")
    op.drop_column("draft_reviews", "sent_at")
    op.drop_column("draft_reviews", "review_note")
