"""Expand draft_reviews intent/urgency/department/classification to 64 chars

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("intent", "urgency", "department", "classification")


def upgrade() -> None:
    for column in _COLUMNS:
        op.alter_column(
            "draft_reviews",
            column,
            existing_type=sa.String(length=32),
            type_=sa.String(length=64),
            existing_nullable=False,
        )


def downgrade() -> None:
    for column in _COLUMNS:
        op.alter_column(
            "draft_reviews",
            column,
            existing_type=sa.String(length=64),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
