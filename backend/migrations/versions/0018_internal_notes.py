"""Create internal_notes table for cross-department collaboration

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "internal_notes" in insp.get_table_names():
        return

    op.create_table(
        "internal_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email_id", sa.String(length=255), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("author_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("author_role", sa.String(length=50), nullable=False, server_default="FRONT_OFFICE"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("mentioned_department", sa.String(length=50), nullable=True),
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
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_internal_notes_email_id"), "internal_notes", ["email_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "internal_notes" not in insp.get_table_names():
        return
    op.drop_index(op.f("ix_internal_notes_email_id"), table_name="internal_notes")
    op.drop_table("internal_notes")
