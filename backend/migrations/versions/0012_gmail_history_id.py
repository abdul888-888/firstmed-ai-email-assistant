"""Gmail incremental sync: history_id cursor on google_credentials

Revision ID: 0012_gmail_history_id
Revises: 0011_specialist_input
Create Date: 2026-07-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "google_credentials", sa.Column("history_id", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("google_credentials", "history_id")
