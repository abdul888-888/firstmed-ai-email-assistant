"""Phase 14: specialist collaboration columns on draft_reviews

Adds the specialist-input mechanism for escalated (NEEDS_PHYSICIAN_REVIEW)
reviews: a clinician's free-text guidance, who gave it, and when — consumed by
WorkflowService.receive_specialist_input() to regenerate the draft.

This reproduces the schema from the orphaned
``app/migrations/versions/0002_specialist_collaboration.py``, which was never
on Alembic's real script_location (``migrations``, per alembic.ini) and so was
never actually applied to any database migrated via `alembic upgrade head`.
That file was removed; this is its replacement in the real revision chain.

Revision ID: 0011_specialist_input
Revises: 0010_unique_gmail_message
Create Date: 2026-07-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_specialist_input"
down_revision: str | None = "0010_unique_gmail_message"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("draft_reviews", sa.Column("specialist_input", sa.Text(), nullable=True))
    op.add_column("draft_reviews", sa.Column("specialist_id", sa.Uuid(), nullable=True))
    op.add_column(
        "draft_reviews",
        sa.Column("specialist_input_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("draft_reviews", "specialist_input_at")
    op.drop_column("draft_reviews", "specialist_id")
    op.drop_column("draft_reviews", "specialist_input")
