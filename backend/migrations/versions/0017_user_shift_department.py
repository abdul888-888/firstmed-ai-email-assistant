"""Add users department, shift tracking columns

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-23

Production may already have these columns from manual SQL; each add is guarded.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("users", "department"):
        op.add_column(
            "users",
            sa.Column(
                "department",
                sa.String(length=50),
                nullable=False,
                server_default="FRONT_OFFICE",
            ),
        )
        op.alter_column("users", "department", server_default=None)

    if not _column_exists("users", "is_on_shift"):
        op.add_column(
            "users",
            sa.Column(
                "is_on_shift",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )
        op.alter_column("users", "is_on_shift", server_default=None)

    if not _column_exists("users", "shift_started_at"):
        op.add_column(
            "users",
            sa.Column("shift_started_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("users", "shift_started_at"):
        op.drop_column("users", "shift_started_at")
    if _column_exists("users", "is_on_shift"):
        op.drop_column("users", "is_on_shift")
    if _column_exists("users", "department"):
        op.drop_column("users", "department")
