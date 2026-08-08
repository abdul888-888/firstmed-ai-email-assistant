"""concurrency: unique (user_id, gmail_message_id) on draft_reviews

Prevents duplicate review rows when two staff (or a retried pull racing the
direct single-message endpoint) process the same inbound email concurrently.
Dedup was previously enforced only in application code (read-then-write),
which is not race-safe.

NOTE: this migration will fail with an IntegrityError if the target database
already has duplicate (user_id, gmail_message_id) rows — deduplicate those
first (keep the newest row per pair) before running `alembic upgrade head`.

Revision ID: 0010_unique_gmail_message
Revises: 0009_collaboration
Create Date: 2026-07-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_draft_reviews_gmail_message_id", table_name="draft_reviews")
    op.create_unique_constraint(
        "uq_draft_reviews_user_gmail_message",
        "draft_reviews",
        ["user_id", "gmail_message_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_draft_reviews_user_gmail_message", "draft_reviews", type_="unique"
    )
    op.create_index(
        "ix_draft_reviews_gmail_message_id", "draft_reviews", ["gmail_message_id"]
    )
